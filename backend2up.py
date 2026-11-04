"""Driver monitoring backend: capture, detection, alert escalation, report logging.

Threads (so video never waits on ML):
  CameraStream  - grabs frames, auto-reconnects, tags each with a sequence number.
  _loop         - face landmarks, seatbelt heuristic, alert state machines (~15 Hz).
  _yolo_loop    - heavy YOLO models (phone / custom seatbelt) on the newest frame only.
UI calls frame() (annotated newest frame) and snapshot() (state for the dashboard).
"""
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
BACKEND_VERSION = 3  # bump when Config/engine change so cached engines get rebuilt
STALE_AFTER = 2.0   # seconds without a new frame before the feed counts as lost


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
    critical_after: dict = field(default_factory=lambda: {
        "seatbelt": 15.0, "speed": 20.0, "drowsiness": 4.0, "phone": 8.0, "camera": 10.0})
    log_interval: int = 300                # seconds between saved reports
    log_dir: str = "logs"


class CameraStream:
    """Frame grabber thread: newest-frame-only, sequence numbers, auto-reconnect."""

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
                if fails > 100:                       # ~2 s of failed reads: reconnect
                    self.cap.release()
                    time.sleep(1.0)
                    self.cap, fails = self._open(), 0
        self.cap.release()

    def read_new(self, after: int, copy: bool = True):
        """Return (seq, frame) only if a frame newer than `after` exists, else None."""
        with self._lock:
            if self._frame is None or self.seq == after:
                return None
            return self.seq, (self._frame.copy() if copy else self._frame)

    def stop(self):
        self._stop.set()


class SpeedSource:
    """Placeholder speed feed. Replace read() with OBD-II (python-obd) or GPS data."""

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


def _ear(p: np.ndarray, idx: list[int]) -> float:
    a = p[idx]
    return (np.linalg.norm(a[1] - a[5]) + np.linalg.norm(a[2] - a[4])) / (2 * np.linalg.norm(a[0] - a[3]) + 1e-6)


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
        self.face_mesh = self.yolo = self.belt_model = None
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
        atexit.register(lambda: self.running and self.write_report())

    # ---------- lifecycle ----------
    @property
    def running(self) -> bool:
        return bool(self.threads) and self.threads[0].is_alive()

    def _load_models(self):
        try:
            if mp and not self.face_mesh:
                self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1, refine_landmarks=True,
                    min_detection_confidence=0.5, min_tracking_confidence=0.5)
            if YOLO and not self.yolo:
                self.yolo = YOLO("yolov8n.pt")                    # COCO: class 67 = cell phone
            if YOLO and not self.belt_model and os.path.exists("models/seatbelt.pt"):
                self.belt_model = YOLO("models/seatbelt.pt")      # optional custom model
        except Exception as exc:
            self.error = f"Model load failed: {exc}"
        self.models = {"face": self.face_mesh is not None, "phone": self.yolo is not None,
                       "seatbelt": "custom model" if self.belt_model else "heuristic"}

    def start(self):
        if self.running:
            return
        self._load_models()
        self.cam, self._latest, self._ui_seq = CameraStream(self.cfg.camera_index), None, 0
        self._stop.clear()
        self.window_start = time.time()
        self.threads = [threading.Thread(target=f, daemon=True) for f in (self._loop, self._yolo_loop)]
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
    def _loop(self, period: float = 1 / 15):
        last_seq, prev = 0, time.time()
        while not self._stop.is_set():
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
                if t0 - self.window_start >= self.cfg.log_interval:
                    self.write_report()
            except Exception as exc:                  # keep the thread alive
                self.error = repr(exc)
            time.sleep(max(0.005, period - (time.time() - t0)))

    def _yolo_loop(self):
        seen = -1
        while not self._stop.is_set():
            item = self._latest
            if not item or item[0] == seen or not (self.yolo or self.belt_model):
                time.sleep(0.02)
                continue
            seen, frame = item
            try:
                if self.yolo:
                    r = self.yolo(frame, classes=[67], conf=0.35, imgsz=320, verbose=False)[0]
                    self.phone_boxes = r.boxes.xyxy.cpu().numpy().astype(int).tolist()
                if self.belt_model:
                    r = self.belt_model(frame, conf=0.4, verbose=False)[0]
                    names = [r.names[int(c)].lower() for c in r.boxes.cls]
                    if any(n.startswith("no") for n in names):
                        self.belt_votes.append(False)
                    elif any("belt" in n for n in names):
                        self.belt_votes.append(True)
            except Exception as exc:
                self.error = repr(exc)

    # ---------- analysis ----------
    def _analyse(self, frame: np.ndarray, now: float):
        cfg, h, w = self.cfg, *frame.shape[:2]
        small = cv2.resize(frame, (64, 48))
        blocked = bool(small.mean() < 15 or small.std() < 6)     # covered or blacked-out lens
        face = ear = roi = None
        if self.face_mesh and not blocked:
            res = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_face_landmarks:
                pts = np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark])
                face = (*pts.min(0), *pts.max(0))
                ear = (_ear(pts, R_EYE) + _ear(pts, L_EYE)) / 2

        # seatbelt (heuristic path; the custom model votes from the YOLO thread)
        if not self.belt_model:
            if face is None:
                self.belt_votes.clear()
            elif self._analysed % 2 == 0:
                belt, roi = self._belt(frame, face)
                if belt is not None:
                    self.belt_votes.append(belt)
            else:
                roi = self.overlay.get("roi")
        self._analysed += 1
        votes = list(self.belt_votes)

        # drowsiness: instantaneous closure plus PERCLOS over the last 60 s
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

        # phone: keep only detections near the driver, hold briefly to ride out flicker
        phones = list(self.phone_boxes)
        if face and cfg.phone_near_driver:
            cx, fw, fh = (face[0] + face[2]) / 2, face[2] - face[0], face[3] - face[1]
            phones = [b for b in phones if abs((b[0] + b[2]) / 2 - cx) < 2.5 * fw
                      and face[1] - 0.5 * fh < (b[1] + b[3]) / 2 < face[3] + 3 * fh]
        if phones:
            self.phone_hit = now

        speed = self.speed_src.read(cfg)
        moving = speed >= cfg.min_speed_checks
        flags = {
            "seatbelt": moving and (face is not None or self.belt_model is not None)
                        and len(votes) >= 5 and sum(votes) / len(votes) < 0.35,
            "speed": speed > cfg.speed_limit,
            "drowsiness": drowsy,
            "phone": moving and now - self.phone_hit < 0.8,
            "camera": blocked,
        }
        with self.lock:
            self.speed, self.ear, self.driver, self.moving, self.perclos = speed, ear, face is not None, moving, perclos
            self.overlay = {"face": face, "roi": roi, "phones": phones}
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
        cfg = self.cfg
        with self.lock:
            for p, bad in flags.items():
                for ev in self.trackers[p].update(bad, now, cfg.confirm_after, cfg.critical_after[p], cfg.realert_every):
                    if ev == "repeat":
                        self.critical_seq += 1                    # re-trigger the sound only
                    else:
                        self._event(p, ev)

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
            for a, b, c, d in lines[:, 0]:
                ang = abs(np.degrees(np.arctan2(d - b, c - a)))
                if 30 <= ang <= 75 or 105 <= ang <= 150:
                    return True, roi
        return False, roi

    # ---------- output for the UI ----------
    def frame(self):
        """Newest unseen frame with latest detections drawn on it; None if nothing new."""
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
        now, cam = time.time(), self.cam
        with self.lock:
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

    # ---------- logging ----------
    def _log(self, title: str, text: str):
        row = (datetime.now().strftime("%H:%M:%S"), title, text)
        self.events.append(row)
        os.makedirs(self.cfg.log_dir, exist_ok=True)
        with open(os.path.join(self.cfg.log_dir, "events.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d} {row[0]}  {row[1]}: {row[2]}\n")

    def _event(self, p: str, ev: str):
        if ev == "critical":
            self.critical_seq += 1
            ev = f"Critical alert: unresolved after {self.cfg.critical_after[p]:.0f}s"
        self._log(TITLES[p], "Issue detected" if ev == "raised" else ev[0].upper() + ev[1:])

    def write_report(self) -> str:
        """Atomically save per-parameter sustained-issue stats for this window, then start a new one."""
        with self.lock:
            end = time.time()
            win = max(end - self.window_start, 1e-6)
            os.makedirs(self.cfg.log_dir, exist_ok=True)
            base = os.path.join(self.cfg.log_dir, f"report_{datetime.fromtimestamp(end):%Y%m%d_%H%M%S}")
            path, k = base + ".csv", 1
            while os.path.exists(path):
                path, k = f"{base}_{k}.csv", k + 1
            fmt = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            with open(path + ".tmp", "w", newline="", encoding="utf-8") as fh:
                wr = csv.writer(fh)
                wr.writerow(["window_start", "window_end", "parameter", "sustained_seconds", "percent_of_window",
                             "episodes", "longest_episode_seconds", "critical_alerts", "ongoing_at_end"])
                for p, t in self.trackers.items():
                    wr.writerow([fmt(self.window_start), fmt(end), TITLES[p], round(t.total, 1),
                                 round(100 * t.total / win, 1), t.episodes, round(t.longest, 1),
                                 t.criticals, int(t.start is not None)])
                    t.reset_window()
            os.replace(path + ".tmp", path)
            self.window_start = end
            return path
