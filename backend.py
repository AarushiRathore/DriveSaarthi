from __future__ import annotations

import atexit
import csv
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import cv2
import numpy as np
import auth
import reporting
from notifier import IST, Notifier
from voice import VoiceAlert, phone_message
from detectors import FaceLandmarker, YoloModels, belt_from_pose, phones_near_driver

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None
try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None

PARAMS = ("seatbelt", "speed", "drowsiness", "phone", "camera")
TITLES = {"seatbelt": "Seatbelt", "speed": "Speed", "drowsiness": "Drowsiness",
          "phone": "Mobile phone", "camera": "Camera feed"}
R_EYE = [33, 160, 158, 133, 153, 144]
L_EYE = [362, 385, 387, 263, 373, 380]
BRASS, RED, INK = (90, 151, 184), (63, 69, 210), (236, 232, 223)  # BGR
BACKEND_VERSION = 4  # bump when Config/engine change so cached engines get rebuilt
STALE_AFTER = 2.0   # seconds without a new frame before the feed counts as lost


def _ear(pts: np.ndarray, idx: list[int]) -> float:
    p = pts[idx]
    return float((np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])) / (2 * np.linalg.norm(p[0] - p[3]) + 1e-6))


@dataclass
class Config:
    camera_index: int = 0
    speed_mode: str = "Simulated"          # "Simulated" | "Manual"
    manual_speed: float = 60.0
    speed_limit: float = 80.0
    ear_threshold: float = 0.21            # eye aspect ratio below this = eyes closed (see calibrate())
    perclos_limit: float = 0.30            # share of last 60 s with eyes closed that signals fatigue
    confirm_after: float = 1.5             # seconds a condition must persist to become an issue
    min_speed_checks: float = 5.0          # seatbelt/phone are only enforced at or above this km/h
    phone_near_driver: bool = True         # ignore phones far from the driver (dash mounts)
    realert_every: float = 10.0            # repeat the critical alert while unresolved
    notify_resolved: bool = True           # also text the emergency contact when speed is back to normal
    renotify_every: float = 300.0          # re-send the overspeed alert (new duration) while it continues
    max_sms_per_hour: int = 6              # cost and spam guard
    voice_enabled: bool = True             # spoken warnings when a critical alert is ignored
    voice_params: tuple = ("phone", "speed")   # which alerts speak
    voice_on_raised: tuple = ("speed",)    # speak on the first warning too; others wait until critical
    phone_conf: float = 0.25               # YOLO phone confidence (lower finds more, may add false alarms)
    yolo_imgsz: int = 480                  # YOLO input size: smaller is faster, larger finds small phones
    belt_conf: float = 0.65                # confidence for a custom seatbelt model
    voice_lang: str = "en"                 # "en" or "hi" (Hindi needs an installed Hindi voice)
    critical_after: dict = field(default_factory=lambda: {
        "seatbelt": 15.0, "speed": 20.0, "drowsiness": 4.0, "phone": 8.0, "camera": 10.0})
    log_interval: int = 300                # seconds between saved reports
    log_dir: str = "logs"


class CameraStream:
    def __init__(self, index: int):
        self.index, self.seq, self.last_ts = index, 0, time.time()  # grace period at startup
        self._frame, self._lock, self._stop = None, threading.Lock(), threading.Event()
        self.cap = self._open()
        threading.Thread(target=self._run, daemon=True).start()

    def _open(self):
        cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    @property
    def ok(self) -> bool:
        return self.cap.isOpened()

    def _run(self):
        fails = 0
        while not self._stop.is_set():
            ok, f = self.cap.read()
            if ok:
                fails = 0
                with self._lock:
                    self._frame, self.seq, self.last_ts = f, self.seq + 1, time.time()
            else:
                fails += 1
                time.sleep(0.02)
                if fails >= 80:                       # ~2 s of failed reads: reconnect
                    self.cap.release()
                    time.sleep(1.0)
                    self.cap, fails = self._open(), 0
        self.cap.release()

    def read_new(self, after: int, copy: bool = True):
        with self._lock:
            if self._frame is None or self.seq == after:
                return None
            return self.seq, (self._frame.copy() if copy else self._frame)

    def stop(self):
        self._stop.set()


class SpeedSource:
    def __init__(self):
        self.v = 60.0

    def read(self, cfg: Config) -> float:
        if cfg.speed_mode == "Manual":
            return cfg.manual_speed
        self.v = min(130.0, max(0.0, self.v + random.uniform(-0.6, 0.6) + (75 - self.v) * 0.002))
        return self.v


class Tracker:
    """Per-parameter state machine: ok -> warning -> critical (+ repeats) with window statistics."""

    def __init__(self):
        self.clear()
        self.reset_window()

    def clear(self):
        self.pending = self.start = self.last = None
        self.level, self.last_alert = "ok", 0.0

    def reset_window(self):
        """Start a new report window; an issue still open counts as one ongoing episode."""
        self.total, self.longest, self.criticals = 0.0, 0.0, 0
        self.episodes = 1 if self.start is not None else 0

    def duration(self, now: float) -> float:
        return now - self.start if self.start else 0.0


    def update(self, bad: bool, now: float, confirm: float, limit: float, realert: float) -> list[str]:
        events = []
        if self.start is not None and self.last is not None:
            self.total += now - self.last
        self.last = now
        if bad:
            self.pending = self.pending or now
            if self.start is None and now - self.pending >= confirm:
                self.start, self.level = self.pending, "warning"
                self.total += now - self.start          # back-date to true onset
                self.episodes += 1
                events.append("raised")
        else:
            self.pending = None
            if self.start is not None:
                events.append(f"resolved after {now - self.start:.0f}s")
                self.clear()
        if self.start is not None:
            d = now - self.start
            self.longest = max(self.longest, d)
            if d >= limit and self.level != "critical":
                self.level, self.last_alert = "critical", now
                self.criticals += 1
                events.append("critical")
            elif self.level == "critical" and now - self.last_alert >= realert:
                self.last_alert = now
                events.append("repeat")
        return events

class MonitorEngine:
    def __init__(self, cfg: Config | None = None):
        self.version = BACKEND_VERSION
        self.cfg = cfg or Config()
        self.lock = threading.RLock()
        self.trackers = {p: Tracker() for p in PARAMS}
        self.events: deque = deque(maxlen=200)
        self.critical_seq = 0
        self.cam: CameraStream | None = None
        self.threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._latest = None                      # (seq, frame) shared read-only with the YOLO thread
        self._ui_seq = 0
        self.speed_src = SpeedSource()
        self.window_start = time.time()
        self.face_mesh = self.yolo = self.belt_model = self.pose_model = None
        self.pose_kp = None
        self.models = {"face": False, "phone": False, "seatbelt": "heuristic"}
        self.overlay: dict = {}
        self.phone_boxes: list = []
        self.phone_hit = 0.0
        self.belt_votes: deque = deque(maxlen=10)
        self.eye_hist: deque = deque()           # (timestamp, eyes_closed) for PERCLOS
        self.calib_until, self.calib_vals = 0.0, []
        self.speed, self.ear, self.driver, self.moving = 0.0, None, False, True
        self.perclos, self.fps, self.error = 0.0, 0.0, ""
        self._analysed = 0
        self._now = time.time()
        self.driver_info, self.location, self.location_label = None, None, ""
        self.notifier, self._speed_notified = Notifier(), False
        self.voice = VoiceAlert(lambda: self.cfg.voice_lang)
        self._voice_n = {p: 0 for p in PARAMS}
        self._sms_times: deque = deque()
        self._last_sms, self._retry_at = 0.0, 0.0
        atexit.register(lambda: self.running and self.write_report())

    # lifecycle 
    @property
    def running(self) -> bool:
        return bool(self.threads) and self.threads[0].is_alive()

    def _load_models(self):
        try:
            if not self.face_mesh:
                try:
                    fl = FaceLandmarker()
                    if fl.backend != "none":
                        self.face_mesh = fl
                except Exception:
                    pass
                if not self.face_mesh and mp and hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
                    self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                        max_num_faces=1, refine_landmarks=True,
                        min_detection_confidence=0.5, min_tracking_confidence=0.5)
        except Exception as exc:
            self.error = f"Face model load failed: {exc}"

        try:
            if YOLO and not self.yolo:
                self.yolo = YOLO("yolov8n.pt")
            if YOLO and not self.pose_model and os.path.exists("yolov8n-pose.pt"):
                self.pose_model = YOLO("yolov8n-pose.pt")
            if YOLO and not self.belt_model and os.path.exists("models/seatbelt.pt"):
                self.belt_model = YOLO("models/seatbelt.pt")
        except Exception as exc:
            self.error = f"YOLO model load failed: {exc}"

        face_ok = False
        if self.face_mesh:
            face_ok = getattr(self.face_mesh, "backend", "") != "none" if hasattr(self.face_mesh, "backend") else True
        self.models = {"face": face_ok, "phone": self.yolo is not None,
                       "seatbelt": "custom model" if self.belt_model else "heuristic"}

    def start(self):
        if self.running:
            return
        self._load_models()
        self.cam, self._latest, self._ui_seq = CameraStream(self.cfg.camera_index), None, 0
        self._stop = threading.Event()
        self.window_start = time.time()
        self.threads = [threading.Thread(target=f, args=(self._stop,), daemon=True, name=n)
                        for f, n in ((self._loop, "monitor-loop"), (self._yolo_loop, "monitor-yolo"))]
        for t in self.threads:
            t.start()

    def stop(self, flush: bool = True):
        self._stop.set()
        for t in self.threads:
            t.join(timeout=3)
        self.threads = []
        if self.cam:
            self.cam.stop()
            self.cam = None
        if flush:
            self.write_report()
        for t in self.trackers.values():
            t.clear()
        self._speed_notified, self._voice_n = False, {p: 0 for p in PARAMS}

    def calibrate(self, seconds: float = 5.0):
        """Learn this driver's open-eye baseline; threshold becomes 72% of the median."""
        self.calib_vals, self.calib_until = [], time.time() + seconds

    def _finish_calibration(self):
        vals, self.calib_until = self.calib_vals, 0.0
        if len(vals) >= 20:
            self.cfg.ear_threshold = round(max(0.10, float(np.median(vals)) * 0.72), 3)
            self._log("Drowsiness", f"Calibrated: eye threshold set to {self.cfg.ear_threshold:.2f}")
        else:
            self._log("Drowsiness", "Calibration failed: face was not visible")

    # ---------- threads ----------
    def _loop(self, stop: threading.Event, period: float = 1 / 15):
        last_seq, prev = 0, time.time()
        while not stop.is_set():
            t0, cam = time.time(), self.cam
            try:
                item = cam.read_new(last_seq, copy=False) if cam else None
                if item:
                    last_seq, frame = item
                    self._latest = item
                    self._analyse(frame, t0)
                    self.fps = 0.9 * self.fps + 0.1 / max(t0 - prev, 1e-3)
                    prev = t0
                elif cam and t0 - cam.last_ts > STALE_AFTER:
                    self._hold(t0)
                if self.calib_until and t0 >= self.calib_until:
                    self._finish_calibration()
                if t0 - self.window_start >= self.cfg.log_interval and t0 >= self._retry_at:
                    self.write_report()
            except Exception as exc:                  # keep the thread alive
                self.error = repr(exc)
            time.sleep(max(0.005, period - (time.time() - t0)))

    def _yolo_loop(self, stop: threading.Event):
        seen = -1
        max_fps = 10
        while not stop.is_set():
            item = self._latest
            if not item or item[0] == seen or not (self.yolo or self.belt_model or self.pose_model):
                time.sleep(0.02)
                continue
            seen, frame, t0 = item[0], item[1], time.time()
            try:
                if self.yolo:
                    cfg = self.cfg
                    results = self.yolo(frame, imgsz=cfg.yolo_imgsz, verbose=False)[0]
                    boxes = []
                    for box in results.boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        # COCO class 67 = cell phone
                        if cls == 67 and conf >= cfg.phone_conf:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            boxes.append([x1, y1, x2, y2])
                    self.phone_boxes = boxes
                if self.pose_model:
                    cfg = self.cfg
                    r = self.pose_model(frame, imgsz=cfg.yolo_imgsz, conf=0.4, verbose=False)[0]
                    if r.keypoints is not None and len(r.boxes) > 0:
                        xyxy = r.boxes.xyxy.cpu().numpy()
                        i = int(np.argmax((xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])))
                        xy = r.keypoints.xy[i].cpu().numpy()
                        cf = r.keypoints.conf[i].cpu().numpy() if r.keypoints.conf is not None else np.ones(len(xy))
                        self.pose_kp = np.concatenate([xy, cf[:, None]], axis=1)
                if self.belt_model:
                    cfg = self.cfg
                    results = self.belt_model(frame, imgsz=cfg.yolo_imgsz, verbose=False)[0]
                    for box in results.boxes:
                        conf = float(box.conf[0])
                        if conf >= cfg.belt_conf:
                            self.belt_votes.append(True)
                            break
                    else:
                        self.belt_votes.append(False)
            except Exception as exc:
                self.error = repr(exc)
            time.sleep(max(0.0, 1 / max_fps - (time.time() - t0)))

    # ---------- analysis ----------
    def _analyse(self, frame: np.ndarray, now: float):
        cfg, h, w = self.cfg, *frame.shape[:2]
        small = cv2.resize(frame, (64, 48))
        blocked = bool(small.mean() < 15 or small.std() < 6)     # covered or blacked-out lens
        face = ear = roi = None
        if self.face_mesh and not blocked:
            if hasattr(self.face_mesh, "detect"):
                det = self.face_mesh.detect(frame)
                if det is not None:
                    face, ear = det
            elif hasattr(self.face_mesh, "process"):
                res = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if res and getattr(res, "multi_face_landmarks", None):
                    pts = np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark])
                    face = (*pts.min(0), *pts.max(0))
                    ear = (_ear(pts, R_EYE) + _ear(pts, L_EYE)) / 2

        # seatbelt (heuristic path; the custom model votes from the YOLO thread)
        kp = getattr(self, "pose_kp", None)
        if not self.belt_model:
            if kp is not None:
                if self._analysed % 2 == 0:
                    belt, roi = belt_from_pose(frame, kp)
                    if belt is not None:
                        self.belt_votes.append(belt)
                else:
                    roi = self.overlay.get("roi")
            elif face is not None:
                if self._analysed % 2 == 0:
                    belt, roi = self._belt(frame, face)
                    if belt is not None:
                        self.belt_votes.append(belt)
                else:
                    roi = self.overlay.get("roi")
            else:
                self.belt_votes.clear()
        self._analysed += 1
        votes = list(self.belt_votes)
        # drowsiness
        closed = ear is not None and ear < cfg.ear_threshold
        if ear is not None:
            self.eye_hist.append((now, closed))
            if self.calib_until:
                self.calib_vals.append(ear)
        while self.eye_hist and now - self.eye_hist[0][0] > 60:
            self.eye_hist.popleft()
        hist = list(self.eye_hist)
        perclos = sum(c for _, c in hist) / len(hist) if hist and now - hist[0][0] >= 20 else 0.0
        drowsy = closed or (perclos > cfg.perclos_limit and ear is not None and ear < cfg.ear_threshold * 1.15)

        # phone — filter boxes to driver-side area when face is known
        raw = list(self.phone_boxes)
        phones = phones_near_driver(raw, kp, face) if cfg.phone_near_driver else raw
        if phones:
            self.phone_hit = now

        driver_seen = face is not None or kp is not None
        speed = self.speed_src.read(cfg)
        moving = speed >= cfg.min_speed_checks
        flags = {
            "seatbelt": moving and driver_seen and len(votes) >= 5 and sum(votes) / len(votes) < 0.35,
            "speed": speed > cfg.speed_limit,
            "drowsiness": drowsy,
            "phone": moving and now - self.phone_hit < 0.8,
            "camera": blocked,
        }
        with self.lock:
            self.speed, self.ear, self.moving, self.perclos = speed, ear, moving, perclos
            self.driver = driver_seen
            self.overlay = {"face": face, "roi": roi, "phones": phones, "kp": kp}
        self._apply(flags, now)

    def _hold(self, now: float):
        """Feed lost: 'unknown' is never 'resolved'. Open issues keep escalating; camera is flagged."""
        speed = self.speed_src.read(self.cfg)
        flags = {p: t.start is not None or t.pending is not None for p, t in self.trackers.items()}
        flags.update(speed=speed > self.cfg.speed_limit, camera=True)
        with self.lock:
            self.speed, self.ear, self.driver, self.overlay = speed, None, False, {}
        self._apply(flags, now)

    def _apply(self, flags: dict, now: float):
        cfg, self._now = self.cfg, now
        with self.lock:
            for p, bad in flags.items():
                for ev in self.trackers[p].update(bad, now, cfg.confirm_after, cfg.critical_after[p], cfg.realert_every):
                    if ev == "repeat":
                        self.critical_seq += 1                    # re-trigger the sound
                        if p == "speed":
                            self._notify_speed("repeat")
                    else:
                        self._event(p, ev)
                    self._voice_hook(p, ev, now)

    def _voice_hook(self, p: str, ev: str, now: float):
        """Speak when an alert is raised (if configured) or still being ignored; wording escalates each time."""
        cfg = self.cfg
        if ev.startswith("resolved"):
            self._voice_n[p] = 0
            return
        first = ev == "raised" and p in cfg.voice_on_raised
        if not (cfg.voice_enabled and p in cfg.voice_params and (first or ev in ("critical", "repeat"))):
            return
        n = self._voice_n[p] = self._voice_n[p] + 1
        msg = phone_message(n, self.trackers[p].duration(now)) if p == "phone" else None
        if msg:
            self.voice.say(msg)
            self._log(TITLES[p], f"Voice warning {n}" + ("" if self.voice.available else " (muted: no speech engine found)"))

    def _belt(self, frame, face):
        x0, y0, x1, y1 = face
        fw, fh, cx = x1 - x0, y1 - y0, (x0 + x1) / 2
        H, W = frame.shape[:2]
        roi = (int(max(0, cx - 1.6 * fw)), int(min(H - 1, y1 + 0.3 * fh)),
               int(min(W, cx + 1.6 * fw)), int(min(H, y1 + 2.2 * fh)))
        rx0, ry0, rx1, ry1 = roi
        if rx1 - rx0 < 40 or ry1 - ry0 < 40:
            return None, roi
        # A fastened belt shows as a long diagonal edge across the chest.
        g = cv2.GaussianBlur(cv2.cvtColor(frame[ry0:ry1, rx0:rx1], cv2.COLOR_BGR2GRAY), (5, 5), 0)
        lines = cv2.HoughLinesP(cv2.Canny(g, 60, 150), 1, np.pi / 180, 40,
                                minLineLength=int(0.5 * (ry1 - ry0)), maxLineGap=12)
        if lines is not None:
            for a, b, c, d in np.asarray(lines).reshape(-1, 4):      # shape differs across OpenCV versions
                ang = abs(np.degrees(np.arctan2(d - b, c - a)))
                if 30 <= ang <= 75 or 105 <= ang <= 150:
                    return True, roi
        return False, roi
    # output for the UI
    def frame(self):
        
        cam = self.cam
        item = cam.read_new(self._ui_seq) if cam else None
        if item is None:
            return None
        self._ui_seq, f = item
        with self.lock:
            ov, ear = dict(self.overlay), self.ear
            crit = any(t.level == "critical" for t in self.trackers.values())
        if ov.get("face"):
            x0, y0, x1, y1 = map(int, ov["face"])
            cv2.rectangle(f, (x0, y0), (x1, y1), BRASS, 1, cv2.LINE_AA)
        if ov.get("roi"):
            rx0, ry0, rx1, ry1 = ov["roi"]
            cv2.rectangle(f, (rx0, ry0), (rx1, ry1), BRASS, 1, cv2.LINE_AA)
        for x0, y0, x1, y1 in ov.get("phones", []):
            cv2.rectangle(f, (x0, y0), (x1, y1), RED, 2, cv2.LINE_AA)
        if ear is not None:
            cv2.putText(f, f"Eye openness {ear:.2f}", (10, f.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, INK, 1, cv2.LINE_AA)
        if crit:
            cv2.rectangle(f, (0, 0), (f.shape[1] - 1, f.shape[0] - 1), RED, 8)
        return f

    def snapshot(self) -> dict:
        now = self._now
        cam = self.cam
        params = {p: dict(level=t.level, duration=t.duration(now), limit=self.cfg.critical_after[p],
                          total=t.total, episodes=t.episodes, criticals=t.criticals)
                  for p, t in self.trackers.items()}
        return dict(params=params, speed=self.speed, ear=self.ear, driver=self.driver,
                    moving=self.moving, perclos=self.perclos, calibrating=bool(self.calib_until),
                    threshold=self.cfg.ear_threshold, models=dict(self.models), fps=self.fps,
                    critical_seq=self.critical_seq, error=self.error,
                    camera_ok=bool(cam and cam.ok and now - cam.last_ts < STALE_AFTER),
                    events=list(self.events)[::-1],
                    next_report=max(0.0, self.cfg.log_interval - (now - self.window_start)))

    #  driver context and emergency notification 
    def set_driver(self, user: dict | None):
        prev = self.driver_info
        if prev and (not user or user["id"] != prev["id"]) and self.running:
            self.write_report()                          # close the previous driver's window
        self.driver_info = user
        self.cfg.log_dir = os.path.join("logs", user["username"]) if user else "logs"

    def set_location(self, lat: float, lon: float, source: str = "GPS"):
        self.location = {"lat": lat, "lon": lon, "source": source, "ts": time.time()}

    def _where(self) -> str:
        loc, label = self.location, self.location_label.strip()
        parts = []
        if loc:
            parts.append(f"{loc['lat']:.4f},{loc['lon']:.4f}" + (" old" if time.time() - loc["ts"] > 600 else ""))
        if label:
            parts.append(label)
        return " ".join(parts) or "unavailable"

    @staticmethod
    def _dur(sec: float) -> str:
        sec = int(round(sec))
        return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"

    def _sms_allowed(self, now: float) -> bool:
        while self._sms_times and now - self._sms_times[0] > 3600:
            self._sms_times.popleft()
        if len(self._sms_times) >= self.cfg.max_sms_per_hour:
            return False
        self._sms_times.append(now)
        return True

    def _notify_speed(self, raw: str):
        info, cfg, now = self.driver_info, self.cfg, self._now
        if not info or not info.get("emergency_phone"):
            return
        if raw in ("critical", "repeat"):
            if raw == "repeat" and now - self._last_sms < cfg.renotify_every:
                return
            kind = "alert"
            vals = [info["full_name"], f"{self.speed:.0f}", f"{cfg.speed_limit:.0f}",
                    self._dur(self.trackers["speed"].duration(now)), self._where(),
                    datetime.now(IST).strftime("%d %b, %I:%M %p")]
        elif raw.startswith("resolved") and self._speed_notified:
            self._speed_notified = False
            if not cfg.notify_resolved:
                return
            kind = "update"
            vals = [info["full_name"], f"{cfg.speed_limit:.0f}", self._dur(float(raw.split()[-1].rstrip("s"))), self._where()]
        else:
            return
        if not self._sms_allowed(now):
            self._log("Speed", "SMS suppressed: hourly limit reached")
            return
        self._last_sms = now
        self._speed_notified = self._speed_notified or kind == "alert"
        self.notifier.send(info["emergency_phone"], kind, vals, cfg.log_dir,
                           lambda st: self._log("Speed", f"Emergency contact notified: {st}"))

    # logging
    def _log(self, title: str, text: str):
        row = (datetime.now(IST).strftime("%H:%M:%S"), title, text)
        self.events.append(row)
        os.makedirs(self.cfg.log_dir, exist_ok=True)
        with open(os.path.join(self.cfg.log_dir, "events.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(IST):%Y-%m-%d} {row[0]} IST  {row[1]}: {row[2]}\n")

    def _event(self, p: str, ev: str):
        raw = ev
        if ev == "critical":
            self.critical_seq += 1
            ev = f"Critical alert: unresolved after {self.cfg.critical_after[p]:.0f}s"
        self._log(TITLES[p], "Issue detected" if ev == "raised" else ev[0].upper() + ev[1:])
        if p == "speed":
            self._notify_speed(raw)

    def write_report(self) -> str:
        with self.lock:
            end, start = time.time(), self.window_start
            win = max(end - start, 1e-6)
            seconds = {TITLES[p]: t.total for p, t in self.trackers.items()}
            issue_total = sum(seconds.values())
            name = (self.driver_info or {}).get("full_name", "Unassigned")
            fmt = lambda t: datetime.fromtimestamp(t, IST).strftime("%Y-%m-%d %H:%M:%S")
            try:
                os.makedirs(self.cfg.log_dir, exist_ok=True)
                base = os.path.join(self.cfg.log_dir, f"report_{datetime.fromtimestamp(end, IST):%Y%m%d_%H%M%S}")
                path, k = base + ".csv", 1
                while os.path.exists(path):
                    path, k = f"{base}_{k}.csv", k + 1
                with open(path + ".tmp", "w", newline="", encoding="utf-8") as fh:
                    wr = csv.writer(fh)
                    wr.writerow(["driver", "window_start", "window_end", "parameter", "sustained_seconds",
                                 "share_of_issue_time_percent", "percent_of_window", "episodes",
                                 "longest_episode_seconds", "critical_alerts", "ongoing_at_end"])
                    for p, t in self.trackers.items():
                        wr.writerow([name, fmt(start), fmt(end), TITLES[p], round(t.total, 1),
                                     round(100 * t.total / issue_total, 1) if issue_total else 0.0,
                                     round(100 * t.total / win, 1), t.episodes, round(t.longest, 1),
                                     t.criticals, int(t.start is not None)])
                os.replace(path + ".tmp", path)
            except OSError as exc:
                self.error, self._retry_at = f"Report not saved: {exc}", end + 30
                return ""
            for t in self.trackers.values():
                t.reset_window()
            self.window_start, self._retry_at = end, 0.0
            png = path[:-4] + ".png"
            try:
                reporting.save_pie(png, seconds, f"{name}: {fmt(start)[11:16]} to {fmt(end)[11:16]} IST")
                if self.driver_info:
                    auth.save_report(self.driver_info["id"], start, end, path, png, seconds)
            except Exception as exc:                       # the CSV is already safe on disk
                self.error = f"Report chart failed: {exc}"
            return path
