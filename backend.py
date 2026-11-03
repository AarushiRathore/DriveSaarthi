"""Driver monitoring backend: capture, detection, alert escalation, report logging.

Design for smooth video:
  * CameraStream  - dedicated thread that only grabs frames (buffer size 1, always latest).
  * MonitorEngine - separate analysis thread (~15 Hz) running the ML models.
  * frame()       - draws the most recent results onto the newest raw frame, so the UI
                    never waits for inference.
"""
from __future__ import annotations

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

PARAMS = ("seatbelt", "speed", "drowsiness", "phone")
TITLES = {"seatbelt": "Seatbelt", "speed": "Speed", "drowsiness": "Drowsiness", "phone": "Mobile phone"}
R_EYE = [33, 160, 158, 133, 153, 144]
L_EYE = [362, 385, 387, 263, 373, 380]
BRASS, RED, INK = (90, 151, 184), (63, 69, 210), (236, 232, 223)  # BGR


@dataclass
class Config:
    camera_index: int = 0
    speed_mode: str = "Simulated"          # "Simulated" | "Manual"
    manual_speed: float = 60.0
    speed_limit: float = 80.0
    ear_threshold: float = 0.21            # eye aspect ratio below this = eyes closed
    confirm_after: float = 1.5             # seconds a condition must persist to become an issue
    critical_after: dict = field(default_factory=lambda: {
        "seatbelt": 15.0, "speed": 20.0, "drowsiness": 4.0, "phone": 8.0})
    log_interval: int = 300                # seconds between saved reports
    log_dir: str = "logs"


class CameraStream:
    """Grabs frames on its own thread so reads never block on the camera."""

    def __init__(self, index: int):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ok = self.cap.isOpened()
        self._frame, self._lock, self._stop = None, threading.Lock(), threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.is_set():
            ok, f = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = f
            else:
                time.sleep(0.01)
        self.cap.release()

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

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
    """Per-parameter state machine: ok -> warning -> critical, plus window statistics."""

    def __init__(self):
        self.pending = self.start = self.last = None
        self.level = "ok"
        self.reset_window()

    def reset_window(self):
        self.total, self.episodes, self.longest, self.criticals = 0.0, 0, 0.0, 0

    def duration(self, now: float) -> float:
        return now - self.start if self.start else 0.0

    def update(self, bad: bool, now: float, confirm: float, limit: float) -> list[str]:
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
                self.start, self.level = None, "ok"
        if self.start is not None:
            d = now - self.start
            self.longest = max(self.longest, d)
            if d >= limit and self.level != "critical":
                self.level = "critical"
                self.criticals += 1
                events.append("critical")
        return events


def _ear(p: np.ndarray, idx: list[int]) -> float:
    a = p[idx]
    return (np.linalg.norm(a[1] - a[5]) + np.linalg.norm(a[2] - a[4])) / (2 * np.linalg.norm(a[0] - a[3]) + 1e-6)


class MonitorEngine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.lock = threading.RLock()
        self.trackers = {p: Tracker() for p in PARAMS}
        self.events: deque = deque(maxlen=200)
        self.critical_seq = 0
        self.cam: CameraStream | None = None
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.speed_src = SpeedSource()
        self.window_start = time.time()
        self.face_mesh = self.yolo = self.belt_model = None
        self.overlay: dict = {}
        self.phone_boxes, self.phone_seen = [], 0.0
        self.belt_votes: deque = deque(maxlen=10)
        self.speed, self.ear, self.driver, self.fps, self.error = 0.0, None, False, 0.0, ""

    # ---------- lifecycle ----------
    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return
        if mp and not self.face_mesh:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)
        if YOLO and not self.yolo:
            self.yolo = YOLO("yolov8n.pt")                       # COCO: class 67 = cell phone
        if YOLO and not self.belt_model and os.path.exists("models/seatbelt.pt"):
            self.belt_model = YOLO("models/seatbelt.pt")         # optional custom model
        self.cam = CameraStream(self.cfg.camera_index)
        self._stop.clear()
        self.window_start = time.time()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self, flush: bool = True):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.cam:
            self.cam.stop()
            self.cam = None
        if flush:
            self.write_report()
        for t in self.trackers.values():
            t.start = t.pending = t.last = None
            t.level = "ok"

    # ---------- analysis ----------
    def _loop(self):
        n, period = 0, 1 / 15
        while not self._stop.is_set():
            t0 = time.time()
            try:
                f = self.cam.read() if self.cam else None
                if f is not None:
                    self._analyse(f, t0, n)
                    n += 1
                    if t0 - self.window_start >= self.cfg.log_interval:
                        self.write_report()
            except Exception as exc:  # keep the thread alive
                self.error = str(exc)
            dt = time.time() - t0
            self.fps = 0.9 * self.fps + 0.1 * (1 / max(dt, 1e-3)) if dt > period else 1 / period
            time.sleep(max(0.0, period - dt))

    def _analyse(self, frame: np.ndarray, now: float, n: int):
        h, w = frame.shape[:2]
        face = ear = roi = None
        if self.face_mesh:
            res = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_face_landmarks:
                pts = np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark])
                face = (*pts.min(0), *pts.max(0))
                ear = (_ear(pts, R_EYE) + _ear(pts, L_EYE)) / 2

        if self.yolo and n % 3 == 0:                              # phone detection every 3rd pass
            r = self.yolo(frame, classes=[67], conf=0.35, imgsz=320, verbose=False)[0]
            if len(r.boxes):
                self.phone_boxes, self.phone_seen = r.boxes.xyxy.cpu().numpy().astype(int).tolist(), now
            elif now - self.phone_seen > 0.8:
                self.phone_boxes = []

        if face and n % 2 == 0:                                   # seatbelt every 2nd pass
            belt, roi = self._belt(frame, face)
            if belt is not None:
                self.belt_votes.append(belt)
        elif face:
            roi = self.overlay.get("roi")

        speed = self.speed_src.read(self.cfg)
        flags = {
            "seatbelt": bool(face) and len(self.belt_votes) >= 5
                        and sum(self.belt_votes) / len(self.belt_votes) < 0.35,
            "speed": speed > self.cfg.speed_limit,
            "drowsiness": ear is not None and ear < self.cfg.ear_threshold,
            "phone": now - self.phone_seen < 0.8,
        }
        with self.lock:
            self.speed, self.ear, self.driver = speed, ear, face is not None
            self.overlay = {"face": face, "roi": roi, "phones": list(self.phone_boxes)}
            for p, bad in flags.items():
                for ev in self.trackers[p].update(bad, now, self.cfg.confirm_after, self.cfg.critical_after[p]):
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
        if self.belt_model:                                       # custom trained model
            r = self.belt_model(frame, conf=0.4, verbose=False)[0]
            names = [r.names[int(c)].lower() for c in r.boxes.cls]
            if any(nm.startswith("no") for nm in names):
                return False, roi
            return (True if any("belt" in nm for nm in names) else None), roi
        # Heuristic fallback: a fastened belt shows as a long diagonal edge across the chest.
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
        """Newest raw frame with the latest detections drawn on top (cheap, never blocks on ML)."""
        f = self.cam.read() if self.cam else None
        if f is None:
            return None
        with self.lock:
            ov, crit = dict(self.overlay), any(t.level == "critical" for t in self.trackers.values())
            ear = self.ear
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
        now = time.time()
        with self.lock:
            params = {p: dict(level=t.level, duration=t.duration(now), limit=self.cfg.critical_after[p],
                              total=t.total, episodes=t.episodes, criticals=t.criticals)
                      for p, t in self.trackers.items()}
            return dict(params=params, speed=self.speed, ear=self.ear, driver=self.driver,
                        fps=self.fps, critical_seq=self.critical_seq, error=self.error,
                        camera_ok=bool(self.cam and self.cam.ok), events=list(self.events)[::-1],
                        next_report=max(0.0, self.cfg.log_interval - (now - self.window_start)))

    # ---------- logging ----------
    def _event(self, p: str, ev: str):
        text = {"raised": "Issue detected",
                "critical": f"Critical alert: unresolved after {self.cfg.critical_after[p]:.0f}s"}.get(ev, ev.capitalize())
        if ev == "critical":
            self.critical_seq += 1
        row = (datetime.now().strftime("%H:%M:%S"), TITLES[p], text)
        self.events.append(row)
        os.makedirs(self.cfg.log_dir, exist_ok=True)
        with open(os.path.join(self.cfg.log_dir, "events.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d} {row[0]}  {row[1]}: {row[2]}\n")

    def write_report(self) -> str:
        """Save per-parameter sustained-issue durations for the current window, then reset it."""
        with self.lock:
            end = time.time()
            os.makedirs(self.cfg.log_dir, exist_ok=True)
            path = os.path.join(self.cfg.log_dir, f"report_{datetime.fromtimestamp(end):%Y%m%d_%H%M%S}.csv")
            fmt = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                wr = csv.writer(fh)
                wr.writerow(["window_start", "window_end", "parameter", "sustained_seconds",
                             "episodes", "longest_episode_seconds", "critical_alerts"])
                for p, t in self.trackers.items():
                    wr.writerow([fmt(self.window_start), fmt(end), TITLES[p], round(t.total, 1),
                                 t.episodes, round(t.longest, 1), t.criticals])
                    t.reset_window()
            self.window_start = end
            return path
