
import glob
import io
import os
import time
import wave
import theme
import numpy as np
import pandas as pd
import streamlit as st


import backend
from backend import PARAMS, TITLES, MonitorEngine



@st.cache_resource
def _make_engine() -> MonitorEngine:
    return MonitorEngine()


def get_engine() -> MonitorEngine:
   
    e = _make_engine()
    stale = (getattr(e, "version", 0) != getattr(backend, "BACKEND_VERSION", 0)
             or not hasattr(e.cfg, "min_speed_checks"))
    if stale:
        try:
            e.stop(flush=False)          # release the old camera and threads
        except Exception:
            pass
        _make_engine.clear()
        e = _make_engine()
    return e


@st.cache_resource
def beep() -> bytes:
    sr = 16000
    t = np.linspace(0, 0.9, int(sr * 0.9), False)
    tone = (np.sin(2 * np.pi * 880 * t) * (np.sin(2 * np.pi * 4 * t) > 0) * 0.6 * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr), w.writeframes(tone.tobytes())
    return buf.getvalue()


def mmss(s: float) -> str:
    return f"{int(s) // 60:02d}:{int(s) % 60:02d}"


def banner_html(snap) -> str:
    ps = snap["params"]
    crit = [TITLES[p] for p in PARAMS if ps[p]["level"] == "critical"]
    warn = [TITLES[p] for p in PARAMS if ps[p]["level"] == "warning"]
    if not snap["camera_ok"]:
        return '<div class="banner warning"><b>Camera unavailable.</b>Check the camera index in the sidebar.</div>'
    if crit:
        return f'<div class="banner critical"><b>Critical alert.</b>Unresolved: {", ".join(crit)}. Act now.</div>'
    if snap["calibrating"]:
        return '<div class="banner warning"><b>Calibrating.</b>Look straight ahead with eyes open for five seconds.</div>'
    if warn:
        return f'<div class="banner warning"><b>Attention needed.</b>{", ".join(warn)} flagged.</div>'
    return '<div class="banner ok"><b>All clear.</b>Every monitored parameter is within limits.</div>'


def panel_html(snap, cfg) -> str:
    sp, out = snap["speed"], []
    good = {"seatbelt": "Fastened", "speed": f"{sp:.0f} km/h, limit {cfg.speed_limit:.0f}",
            "drowsiness": "Eyes open", "phone": "No phone in hand", "camera": "Feed live"}
    bad = {"seatbelt": "Not fastened", "speed": f"{sp:.0f} km/h, over the {cfg.speed_limit:.0f} limit",
           "drowsiness": "Eyes closed or drooping", "phone": "Phone in use", "camera": "Feed lost or blocked"}
    for p in PARAMS:
        s = snap["params"][p]
        lvl = s["level"]
        if lvl == "ok":
            sub = "No driver in frame" if not snap["driver"] and p in ("seatbelt", "drowsiness") else good[p]
        elif lvl == "warning":
            sub = f"{bad[p]}. Critical in {max(0, s['limit'] - s['duration']):.0f}s"
        else:
            sub = f"{bad[p]}. Critical alert raised"
        pct = min(100, 100 * s["duration"] / s["limit"]) if lvl != "ok" else 0
        out.append(f'<div class="row {lvl}"><div class="name">{TITLES[p]}</div>'
                   f'<div class="timer">{mmss(s["duration"]) if lvl != "ok" else "00:00"}</div>'
                   f'<div class="sub">{sub}</div><div class="bar"><i style="width:{pct}%"></i></div></div>')
    return "".join(out)


def strip_html(snap) -> str:
    ear = "n/a" if snap["ear"] is None else f"{snap['ear']:.2f}"
    return (f'<div class="strip"><div><b>{snap["speed"]:.0f}</b>km/h</div><div><b>{ear}</b>eye openness</div>'
            f'<div><b>{snap["fps"]:.0f}</b>analysis fps</div>'
            f'<div><b>{mmss(snap["next_report"])}</b>until next report</div></div>')


engine = get_engine()
cfg = engine.cfg
user = st.session_state.get("user")
if not user:
    st.error("Please start the app with `streamlit run app.py` and sign in.")
    st.stop()
engine.set_driver(user)

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown(f"**{user['full_name']}**  \n<span style='color:#94A0B4'>Vehicle {user['vehicle_plate'] or 'not set'}</span>",
                unsafe_allow_html=True)
    if st.button("Sign out", use_container_width=True):
        engine.stop()
        engine.set_driver(None)
        st.session_state.pop("user", None)
        st.rerun()
    st.markdown("### Controls")
    run = st.toggle("Monitoring active", key="run")
    cam = int(st.number_input("Camera index", 0, 10, cfg.camera_index))
    cfg.speed_mode = st.radio("Speed source", ["Simulated", "Manual"], horizontal=True)
    cfg.speed_limit = float(st.slider("Speed limit (km/h)", 20, 160, int(cfg.speed_limit)))
    if cfg.speed_mode == "Manual":
        cfg.manual_speed = float(st.slider("Current speed (km/h)", 0, 200, int(cfg.manual_speed)))
    cfg.ear_threshold = st.slider("Eye closure threshold", 0.10, 0.35, cfg.ear_threshold, 0.01)
    cfg.confirm_after = st.slider("Confirm an issue after (s)", 0.5, 5.0, cfg.confirm_after, 0.5)
    cfg.min_speed_checks = float(st.number_input("Seatbelt and phone checks above (km/h)", 0, 60, int(cfg.min_speed_checks)))
    cfg.realert_every = float(st.number_input("Repeat critical alert every (s)", 3, 120, int(cfg.realert_every)))
    st.markdown("#### Critical alert after (seconds)")
    for p in PARAMS:
        cfg.critical_after[p] = float(st.number_input(TITLES[p], 3, 300, int(cfg.critical_after[p]), key=f"c_{p}"))
    cfg.log_interval = int(st.number_input("Report interval (minutes)", 1, 60, cfg.log_interval // 60)) * 60
    if st.button("Save report now", use_container_width=True):
        st.success(f"Saved {os.path.basename(engine.write_report())}")
    if st.button("Calibrate eyes", use_container_width=True, disabled=not run):
        engine.calibrate()
    st.markdown("#### Vehicle location")
    if st.checkbox("Share browser location", help="Included in emergency messages"):
        try:
            from streamlit_js_eval import get_geolocation
            g = get_geolocation()
            if g and "coords" in g:
                engine.set_location(g["coords"]["latitude"], g["coords"]["longitude"], "browser GPS")
        except ImportError:
            st.caption("Install streamlit-js-eval to enable browser location.")
    engine.location_label = st.text_input("Location note", placeholder="e.g. NH48 near Gurugram toll")

if cam != cfg.camera_index:
    cfg.camera_index = cam
    if engine.running:
        engine.stop(flush=False)
        engine.start()
if run and not engine.running:
    with st.spinner("Loading models and opening camera"):
        engine.start()
elif not run and engine.running:
    engine.stop()

_m = engine.snapshot()
if run and not (_m["models"]["face"] and _m["models"]["phone"]):
    st.sidebar.warning("A model failed to load, so some checks are off. " + _m["error"])
elif run:
    st.sidebar.caption(f"Seatbelt check: {_m['models']['seatbelt']}")

# ---------------- layout ----------------
st.markdown('<div class="masthead"><h1>Driver Assurance</h1>'
            '<span>Live cabin monitoring: seatbelt, speed, alertness and phone use</span></div>',
            unsafe_allow_html=True)
banner = st.empty()
left, right = st.columns([1.55, 1], gap="large")
video, strip, panel = left.empty(), left.empty(), right.empty()
audio = st.empty()
tab_log, tab_rep = st.tabs(["Event log", "Saved reports"])
log_ph = tab_log.empty()

with tab_rep:
    files = sorted(glob.glob(os.path.join(cfg.log_dir, "report_*.csv")), reverse=True)
    if files:
        pick = st.selectbox("Report", files, format_func=os.path.basename, label_visibility="collapsed")
        df = pd.read_csv(pick)
        png = pick[:-4] + ".png"
        c1, c2 = st.columns([1, 1.3], gap="large")
        if os.path.exists(png):
            c1.image(png, caption="Share of issue time by factor", width="stretch")
        c2.dataframe(df.drop(columns=["driver", "window_start", "window_end"]), hide_index=True, width="stretch")
        c2.download_button("Download CSV", df.to_csv(index=False), os.path.basename(pick), "text/csv")
        if os.path.exists(png):
            c2.download_button("Download pie chart", open(png, "rb").read(), os.path.basename(png), "image/png")
    else:
        st.caption(f"No reports yet. One is saved every {cfg.log_interval // 60} minutes while monitoring runs.")


def render(snap, slow: bool):
    banner.markdown(banner_html(snap), unsafe_allow_html=True)
    strip.markdown(strip_html(snap), unsafe_allow_html=True)
    panel.markdown(panel_html(snap, cfg), unsafe_allow_html=True)
    if slow:
        rows = snap["events"][:15]
        if rows:
            log_ph.dataframe(pd.DataFrame(rows, columns=["Time", "Parameter", "Event"]),
                             hide_index=True, use_container_width=True)
        else:
            log_ph.caption("No events yet.")


snap = engine.snapshot()
render(snap, True)

if not run:
    video.info("Monitoring is paused. Turn on Monitoring active in the sidebar to begin.")
else:
    last_seq, last_ui, last_slow = snap["critical_seq"], 0.0, 0.0
    while True:                                   # a widget change reruns the script and ends this loop
        frame = engine.frame()
        if frame is not None:
            video.image(frame, channels="BGR", output_format="JPEG", width="stretch")
        now = time.time()
        if now - last_ui > 0.25:
            snap = engine.snapshot()
            render(snap, now - last_slow > 1.0)
            last_ui = now
            if now - last_slow > 1.0:
                last_slow = now
            if snap["critical_seq"] != last_seq:
                last_seq = snap["critical_seq"]
                audio.audio(beep(), format="audio/wav", autoplay=True, alt=f"Alert beep {last_seq}")
        time.sleep(0.03)
