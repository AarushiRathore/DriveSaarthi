"""
detectors.py – Thin wrappers around MediaPipe Tasks and YOLOv8 for DriveSaarthi.

Exported names used by backend.py
-----------------------------------
    FaceLandmarker          – face mesh / landmark detector
    YoloModels              – grouped YOLO model holder (not directly used but kept for compat)
    belt_from_pose          – seatbelt heuristic from pose keypoints
    phones_near_driver      – spatial filter: keep only phone boxes near the driver
"""
from __future__ import annotations

import os
import numpy as np

# ---------------------------------------------------------------------------
# FaceLandmarker
# ---------------------------------------------------------------------------
# We try three backends in order of preference:
#   1. MediaPipe Tasks  (mediapipe >= 0.10.x, needs face_landmarker.task model)
#   2. MediaPipe legacy face-mesh solution  (mediapipe < 0.10 or no .task file)
#   3. OpenCV Haar cascade (always available, lowest accuracy)
#   4. "none" – no face detection available at all
# ---------------------------------------------------------------------------

_TASK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "face_landmarker.task")

R_EYE = [33, 160, 158, 133, 153, 144]
L_EYE = [362, 385, 387, 263, 373, 380]


def _ear(pts: np.ndarray, idx: list[int]) -> float:
    p = pts[idx]
    return float(
        (np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4]))
        / (2 * np.linalg.norm(p[0] - p[3]) + 1e-6)
    )


class FaceLandmarker:
    """
    Unified face landmark detector.

    ``detect(frame_bgr)`` returns ``(bbox, ear)`` or ``None``.
      • bbox = (x0, y0, x1, y1)  in pixel coordinates
      • ear  = float eye-aspect-ratio
    """

    def __init__(self):
        self.backend = "none"
        self._detector = None
        self._haar     = None
        self._setup()

    # ------------------------------------------------------------------
    def _setup(self):
        # --- try MediaPipe Tasks first ---
        try:
            import mediapipe as mp  # noqa: F401
            from mediapipe.tasks.python import vision as mp_vision
            from mediapipe.tasks.python.core.base_options import BaseOptions

            if os.path.exists(_TASK_PATH):
                opts = mp_vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=_TASK_PATH),
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self._detector = mp_vision.FaceLandmarker.create_from_options(opts)
                self.backend = "mediapipe_tasks"
                return
        except Exception:
            pass

        # --- try legacy MediaPipe face-mesh ---
        try:
            import mediapipe as mp

            if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
                self._detector = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.backend = "mediapipe_legacy"
                return
        except Exception:
            pass

        # --- OpenCV Haar cascade fallback ---
        try:
            import cv2

            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(path):
                self._haar = cv2.CascadeClassifier(path)
                self.backend = "haar"
                return
        except Exception:
            pass

        # nothing worked
        self.backend = "none"

    # ------------------------------------------------------------------
    def detect(self, frame_bgr: np.ndarray):
        """
        Returns (bbox_tuple, ear_float) or None if no face found.
        """
        if self.backend == "mediapipe_tasks":
            return self._detect_tasks(frame_bgr)
        if self.backend == "mediapipe_legacy":
            return self._detect_legacy(frame_bgr)
        if self.backend == "haar":
            return self._detect_haar(frame_bgr)
        return None

    # ------------------------------------------------------------------
    def _detect_tasks(self, frame_bgr: np.ndarray):
        import mediapipe as mp
        from mediapipe.tasks.python import vision as mp_vision

        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)
        if not result.face_landmarks:
            return None
        h, w = frame_bgr.shape[:2]
        lm = result.face_landmarks[0]
        pts = np.array([(p.x * w, p.y * h) for p in lm])
        bbox = (*pts.min(0), *pts.max(0))
        ear = (_ear(pts, R_EYE) + _ear(pts, L_EYE)) / 2
        return bbox, ear

    def _detect_legacy(self, frame_bgr: np.ndarray):
        import cv2
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = self._detector.process(rgb)
        if not (res and getattr(res, "multi_face_landmarks", None)):
            return None
        pts = np.array([(p.x * w, p.y * h) for p in res.multi_face_landmarks[0].landmark])
        bbox = (*pts.min(0), *pts.max(0))
        ear = (_ear(pts, R_EYE) + _ear(pts, L_EYE)) / 2
        return bbox, ear

    def _detect_haar(self, frame_bgr: np.ndarray):
        import cv2
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if not len(faces):
            return None
        x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        bbox = (float(x), float(y), float(x + fw), float(y + fh))
        return bbox, None   # Haar can't give EAR


# ---------------------------------------------------------------------------
# YoloModels  (simple container – backend.py manages the models directly)
# ---------------------------------------------------------------------------

class YoloModels:
    """
    Thin holder kept for API compatibility.  Backend.py loads models itself;
    this class is available in case other code imports it.
    """

    def __init__(self):
        self.phone = None
        self.pose  = None
        self.belt  = None


# ---------------------------------------------------------------------------
# belt_from_pose
# ---------------------------------------------------------------------------

def belt_from_pose(frame: np.ndarray, keypoints: np.ndarray):
    """
    Estimate seatbelt presence using body pose keypoints.

    keypoints : (N, 3) array  – (x, y, confidence) per COCO keypoint.
    COCO indices used:
        5 = left shoulder, 6 = right shoulder, 11 = left hip, 12 = right hip

    Returns (belt_present: bool | None, roi_tuple | None).
    ``None`` means insufficient data.
    """
    import cv2

    if keypoints is None or len(keypoints) < 13:
        return None, None

    H, W = frame.shape[:2]
    CONF_THR = 0.3

    def kp(i):
        x, y, c = keypoints[i]
        return (float(x), float(y)), float(c)

    ls, ls_c = kp(5)
    rs, rs_c = kp(6)
    lh, lh_c = kp(11)
    rh, rh_c = kp(12)

    # need at least one shoulder and one hip with decent confidence
    if ls_c < CONF_THR and rs_c < CONF_THR:
        return None, None
    if lh_c < CONF_THR and rh_c < CONF_THR:
        return None, None

    # build a chest ROI between shoulders and hips
    xs = [p[0] for p, c in [(ls, ls_c), (rs, rs_c)] if c >= CONF_THR]
    ys_top = [p[1] for p, c in [(ls, ls_c), (rs, rs_c)] if c >= CONF_THR]
    ys_bot = [p[1] for p, c in [(lh, lh_c), (rh, rh_c)] if c >= CONF_THR]

    if not xs or not ys_top or not ys_bot:
        return None, None

    margin = 0.15
    rx0 = int(max(0, min(xs) - (max(xs) - min(xs)) * margin))
    rx1 = int(min(W, max(xs) + (max(xs) - min(xs)) * margin))
    ry0 = int(max(0, min(ys_top)))
    ry1 = int(min(H, max(ys_bot)))

    roi = (rx0, ry0, rx1, ry1)
    if rx1 - rx0 < 40 or ry1 - ry0 < 40:
        return None, roi

    crop = frame[ry0:ry1, rx0:rx1]
    gray = cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.Canny(gray, 60, 150)
    min_len = int(0.4 * (ry1 - ry0))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 35,
                            minLineLength=min_len, maxLineGap=15)
    if lines is not None:
        for a, b, c, d in np.asarray(lines).reshape(-1, 4):
            ang = abs(np.degrees(np.arctan2(d - b, c - a)))
            if 25 <= ang <= 80 or 100 <= ang <= 155:
                return True, roi
    return False, roi


# ---------------------------------------------------------------------------
# phones_near_driver
# ---------------------------------------------------------------------------

def phones_near_driver(
    boxes: list[list[int]],
    keypoints,
    face_bbox,
    max_dist_ratio: float = 1.8,
) -> list[list[int]]:
    """
    Filter phone bounding boxes to keep only those spatially close to the driver.

    Strategy (in order of data availability):
      1. If pose keypoints are available, measure distance to wrist / hand area.
      2. Else if face_bbox is available, measure distance to face centre.
      3. Else return all boxes (no spatial info to filter with).

    max_dist_ratio : maximum allowed distance as a multiple of face/torso size.
    """
    if not boxes:
        return []

    # --- build a reference point for the driver ---
    ref_x = ref_y = ref_scale = None

    # try keypoints first (wrists = indices 9 & 10, shoulders = 5 & 6)
    if keypoints is not None and len(keypoints) >= 11:
        CONF_THR = 0.25
        candidates = []
        for i in [9, 10]:       # wrists
            x, y, c = keypoints[i]
            if c >= CONF_THR:
                candidates.append((float(x), float(y)))
        if not candidates:
            for i in [5, 6]:    # fall back to shoulders
                x, y, c = keypoints[i]
                if c >= CONF_THR:
                    candidates.append((float(x), float(y)))
        if candidates:
            ref_x = float(np.mean([p[0] for p in candidates]))
            ref_y = float(np.mean([p[1] for p in candidates]))
            # estimate scale from shoulder width if available
            lsxy = keypoints[5][:2] if keypoints[5][2] >= CONF_THR else None
            rsxy = keypoints[6][:2] if keypoints[6][2] >= CONF_THR else None
            if lsxy is not None and rsxy is not None:
                ref_scale = float(np.linalg.norm(np.array(lsxy) - np.array(rsxy)))

    # fall back to face bbox
    if ref_x is None and face_bbox is not None:
        x0, y0, x1, y1 = face_bbox
        ref_x = (x0 + x1) / 2
        ref_y = (y0 + y1) / 2
        ref_scale = max(x1 - x0, y1 - y0)

    # no reference at all – keep everything
    if ref_x is None:
        return boxes

    if ref_scale is None or ref_scale < 1:
        ref_scale = 100.0  # safe fallback

    threshold = ref_scale * max_dist_ratio
    result = []
    for box in boxes:
        bx0, by0, bx1, by1 = box
        cx = (bx0 + bx1) / 2
        cy = (by0 + by1) / 2
        dist = float(np.hypot(cx - ref_x, cy - ref_y))
        if dist <= threshold:
            result.append(box)
    return result
