import os
import sys
import time
from datetime import datetime
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import (
    MobileNetV2,
    preprocess_input,
    decode_predictions,
)

# Automatically invoke Streamlit web server if run with `python main.py`
if __name__ == "__main__" and get_script_run_ctx() is None:
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", sys.argv[0]]
    sys.exit(stcli.main())


# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & LOCAL STORAGE INITIALIZATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI Driver Safety Evaluation System",
    layout="wide",
)

LOG_FILE = "safety_events_log.csv"

def init_storage():
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(
            columns=[
                "Timestamp",
                "Driver_Attention",
                "Drowsiness_Detected",
                "Phone_Detected",
                "Seatbelt_Worn",
                "Speed_kmh",
                "Risk_Score",
                "Risk_Level",
                "Active_Warnings",
            ]
        )
        df.to_csv(LOG_FILE, index=False)

def log_safety_event(attention, drowsy, phone, seatbelt, speed, score, level, warnings):
    new_entry = pd.DataFrame(
        [
            {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Driver_Attention": attention,
                "Drowsiness_Detected": drowsy,
                "Phone_Detected": phone,
                "Seatbelt_Worn": seatbelt,
                "Speed_kmh": speed,
                "Risk_Score": score,
                "Risk_Level": level,
                "Active_Warnings": ", ".join(warnings) if warnings else "None",
            }
        ]
    )
    new_entry.to_csv(LOG_FILE, mode="a", header=False, index=False)

init_storage()

# ---------------------------------------------------------
# 2. LOAD AI / COMPUTER VISION MODELS (CACHED)
# ---------------------------------------------------------
@st.cache_resource
def load_models():
    # OpenCV Haar Cascades for real-time Face and Eye detection
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
    )
    # TensorFlow/Keras MobileNetV2 for Mobile Phone & Seatbelt Recognition
    keras_model = MobileNetV2(weights="imagenet")
    return face_cascade, eye_cascade, keras_model

face_cascade, eye_cascade, keras_model = load_models()

# ---------------------------------------------------------
# 3. HELPER FUNCTIONS FOR AI DETECTION & RISK EVALUATION
# ---------------------------------------------------------
def detect_seatbelt_heuristic(frame):
    """Checks the chest region for a diagonal seat-belt strap using Canny edges & Hough Lines."""
    h, w, _ = frame.shape
    chest_roi = frame[int(h * 0.55) : h, int(w * 0.25) : int(w * 0.75)]
    if chest_roi.size == 0:
        return False
    gray = cv2.cvtColor(chest_roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=50, minLineLength=60, maxLineGap=15
    )
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 != 0:
                slope = abs((y2 - y1) / (x2 - x1))
                # Diagonal slope typical of a shoulder seatbelt (approx 30 to 65 degrees)
                if 0.55 < slope < 2.2:
                    return True
    return False

def classify_objects_keras(frame, model):
    """Uses Keras MobileNetV2 to detect mobile phones or seat belts in the frame."""
    resized = cv2.resize(frame, (224, 224))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    x = np.expand_dims(rgb.astype(np.float32), axis=0)
    x = preprocess_input(x)
    preds = model.predict(x, verbose=0)
    decoded = decode_predictions(preds, top=5)[0]

    phone_detected = False
    seatbelt_detected = False

    for _, label, prob in decoded:
        if label in ["cellular_telephone", "iPod", "pay-phone", "remote_control"] and prob > 0.12:
            phone_detected = True
        if label == "seat_belt" and prob > 0.10:
            seatbelt_detected = True

    return phone_detected, seatbelt_detected

def evaluate_driver_risk(drowsy, distracted, phone, seatbelt_worn, speed, speed_limit):
    """Calculates composite risk score (0-100) and generates active warnings."""
    score = 0
    warnings = []

    if drowsy:
        score += 40
        warnings.append("DROWSINESS DETECTED (Eyes Closed)")
    if distracted:
        score += 25
        warnings.append("DRIVER DISTRACTED (Not Looking Forward)")
    if phone:
        score += 30
        warnings.append("MOBILE PHONE USAGE DETECTED")
    if not seatbelt_worn:
        score += 20
        warnings.append("SEAT BELT NOT WORN")
    if speed > speed_limit:
        overspeed_penalty = min(30, int((speed - speed_limit) * 0.75))
        score += overspeed_penalty
        warnings.append(f"OVERSPEEDING ({speed} km/h > {speed_limit} km/h)")

    score = min(100, score)

    if score >= 60:
        level = "HIGH RISK (CRITICAL)"
    elif score >= 30:
        level = "MODERATE RISK (WARNING)"
    else:
        level = "SAFE"

    return score, level, warnings

# ---------------------------------------------------------
# 4. STREAMLIT DASHBOARD UI & SIDEBAR CONTROLS
# ---------------------------------------------------------
st.title("🚗 AI Driver Safety Evaluation System")
st.markdown(
    "Real-Time Computer Vision Driver Monitoring & Local Risk Evaluation Dashboard"
)

st.sidebar.header("⚙️ System Controls & Telemetry")
run_camera = st.sidebar.toggle("Start Live Monitoring", value=False)
vehicle_speed = st.sidebar.slider("Simulated Vehicle Speed (km/h)", 0, 160, 55)
speed_limit = st.sidebar.number_input("Road Speed Limit (km/h)", 20, 120, 80)

st.sidebar.markdown("---")
st.sidebar.subheader("🛠️ Demo / Viva Override Controls")
st.sidebar.caption("Use these during presentation to simulate specific scenarios on demand:")
sim_phone = st.sidebar.checkbox("Simulate Mobile Phone Usage", value=False)
sim_seatbelt = st.sidebar.selectbox(
    "Seat Belt Detection Mode", ["Auto (AI + Vision)", "Force Worn", "Force Not Worn"]
)
drowsy_frame_threshold = st.sidebar.slider("Drowsiness Sensitivity (Frames)", 5, 30, 12)

# Layout Columns
col_video, col_metrics = st.columns([1.4, 1])

with col_video:
    st.subheader("📷 Live Driver Camera Feed")
    frame_placeholder = st.empty()

with col_metrics:
    st.subheader("📊 Real-Time Safety Evaluation")
    status_banner = st.empty()
    m1, m2, m3 = st.columns(3)
    metric_risk = m1.empty()
    metric_speed = m2.empty()
    metric_seatbelt = m3.empty()

    m4, m5 = st.columns(2)
    metric_drowsy = m4.empty()
    metric_phone = m5.empty()

    st.markdown("#### 🚨 Active Safety Alerts")
    warnings_placeholder = st.empty()

# ---------------------------------------------------------
# 5. REAL-TIME VIDEO PROCESSING LOOP
# ---------------------------------------------------------
if run_camera:
    cap = cv2.VideoCapture(0)
    closed_eye_frames = 0
    missing_face_frames = 0
    frame_count = 0
    last_log_time = 0
    ai_phone = False
    ai_seatbelt = False

    while run_camera and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            st.error("Unable to access webcam. Please check camera permissions.")
            break

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))

        eyes_detected = False
        if len(faces) > 0:
            missing_face_frames = 0
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                roi_gray = gray[y : y + int(h * 0.65), x : x + w]
                roi_color = frame[y : y + int(h * 0.65), x : x + w]
                eyes = eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20))
                if len(eyes) > 0:
                    eyes_detected = True
                    for (ex, ey, ew, eh) in eyes:
                        cv2.rectangle(roi_color, (ex, ey), (ex + ew, ey + eh), (255, 255, 0), 2)
        else:
            missing_face_frames += 1

        # Update Drowsiness & Attention counters
        if len(faces) > 0 and not eyes_detected:
            closed_eye_frames += 1
        else:
            closed_eye_frames = max(0, closed_eye_frames - 1)

        is_drowsy = closed_eye_frames >= drowsy_frame_threshold
        is_distracted = missing_face_frames >= 15

        # Run Keras MobileNetV2 every 10 frames to keep FPS smooth
        if frame_count % 10 == 0:
            ai_phone, keras_sb = classify_objects_keras(frame, keras_model)
            heuristic_sb = detect_seatbelt_heuristic(frame)
            ai_seatbelt = keras_sb or heuristic_sb
        frame_count += 1

        # Apply Demo Overrides if selected
        phone_active = True if sim_phone else ai_phone
        if sim_seatbelt == "Force Worn":
            seatbelt_active = True
        elif sim_seatbelt == "Force Not Worn":
            seatbelt_active = False
        else:
            seatbelt_active = ai_seatbelt

        # Compute Risk Score & Warnings
        risk_score, risk_level, active_warnings = evaluate_driver_risk(
            is_drowsy, is_distracted, phone_active, seatbelt_active, vehicle_speed, speed_limit
        )

        # Draw HUD Overlay on Video Frame
        hud_color = (0, 0, 255) if risk_score >= 60 else ((0, 165, 255) if risk_score >= 30 else (0, 200, 0))
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 45), hud_color, -1)
        cv2.putText(
            frame,
            f"STATUS: {risk_level} | RISK SCORE: {risk_score}% | SPEED: {vehicle_speed} km/h",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        # Render Frame in Streamlit
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)

        # Update Real-Time Dashboard Metrics
        if risk_score >= 60:
            status_banner.error(f"**OVERALL STATUS: {risk_level}**")
        elif risk_score >= 30:
            status_banner.warning(f"**OVERALL STATUS: {risk_level}**")
        else:
            status_banner.success(f"**OVERALL STATUS: {risk_level}**")

        metric_risk.metric("Risk Score", f"{risk_score}%")
        metric_speed.metric("Vehicle Speed", f"{vehicle_speed} km/h")
        metric_seatbelt.metric("Seat Belt", "Worn ✅" if seatbelt_active else "Missing ❌")
        metric_drowsy.metric("Driver State", "Drowsy 😴" if is_drowsy else ("Distracted 👀" if is_distracted else "Alert 😊"))
        metric_phone.metric("Mobile Phone", "Detected 📱" if phone_active else "Clear ✅")

        if active_warnings:
            warnings_placeholder.warning("\n\n".join([f"⚠️ {w}" for w in active_warnings]))
            # Log unsafe events locally at most once every 4 seconds
            if time.time() - last_log_time > 4.0:
                log_safety_event(
                    "Distracted" if is_distracted else "Attentive",
                    is_drowsy,
                    phone_active,
                    seatbelt_active,
                    vehicle_speed,
                    risk_score,
                    risk_level,
                    active_warnings,
                )
                last_log_time = time.time()
        else:
            warnings_placeholder.info("✅ No unsafe driving behaviour detected.")

    cap.release()
else:
    frame_placeholder.info("Click **'Start Live Monitoring'** in the left sidebar to activate the webcam.")

# ---------------------------------------------------------
# 6. LOCAL SAFETY EVENT LOG VIEWER & EXPORT
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📁 Local Safety Event Records (`safety_events_log.csv`)")

if os.path.exists(LOG_FILE):
    log_df = pd.read_csv(LOG_FILE)
    st.dataframe(log_df.tail(15).iloc[::-1], use_container_width=True)

    col_dl, col_clear = st.columns([1, 5])
    with col_dl:
        st.download_button(
            label="⬇️ Download CSV Report",
            data=log_df.to_csv(index=False).encode("utf-8"),
            file_name="driver_safety_report.csv",
            mime="text/csv",
        )
    with col_clear:
        if st.button("🗑️ Clear Local Logs"):
            os.remove(LOG_FILE)
            init_storage()
            st.rerun()