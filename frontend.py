"""Streamlit frontend. Run with:  streamlit run frontend.py"""
import glob
import io
import os
import time
import wave

import numpy as np
import pandas as pd
import streamlit as st

from backend import PARAMS, TITLES, MonitorEngine

st.set_page_config(page_title="Driver Assurance", page_icon="🛡️", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');
:root{--ink:#0D1522;--panel:#131E31;--line:#25324A;--text:#ECE8DF;--muted:#94A0B4;
--brass:#B8975A;--ok:#6FA58C;--warn:#D6A24A;--crit:#D2453F;}
html,body,.stApp{background:var(--ink);color:var(--text);font-family:'IBM Plex Sans',sans-serif;}
header[data-testid="stHeader"],footer,[data-testid="stAudio"]{display:none;}
.block-container{padding-top:1.8rem;max-width:1400px;}
section[data-testid="stSidebar"]{background:var(--panel);border-right:1px solid var(--line);}
[data-testid="stImage"] img{border:1px solid var(--line);border-radius:3px;}
.masthead{display:flex;align-items:baseline;justify-content:space-between;
  border-bottom:1px solid var(--brass);padding-bottom:.7rem;margin-bottom:1.1rem;}
.masthead h1{font-family:'Newsreader',serif;font-weight:400;font-size:2.3rem;margin:0;letter-spacing:.01em;}
.masthead span{color:var(--muted);font-size:.95rem;}
.banner{padding:.85rem 1.1rem;border-left:4px solid;border-radius:2px;margin-bottom:1rem;
  background:var(--panel);font-size:1rem;}
.banner.ok{border-color:var(--ok);}.banner.warning{border-color:var(--warn);}
.banner.critical{border-color:var(--crit);background:#3A1719;animation:pulse 1.1s ease-in-out infinite;}
.banner b{font-weight:600;margin-right:.5rem;}
@keyframes pulse{50%{background:#5A1F22;}}
.strip{display:flex;gap:2.2rem;padding:.8rem .2rem;color:var(--muted);font-size:.9rem;}
.strip b{display:block;color:var(--text);font-family:'Newsreader',serif;font-weight:400;
  font-size:1.5rem;font-variant-numeric:lining-nums tabular-nums;}
.row{display:grid;grid-template-columns:1fr auto;gap:.15rem 1rem;padding:.9rem 1rem;margin-bottom:.6rem;
  background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--ok);border-radius:2px;}
.row.warning{border-left-color:var(--warn);}.row.critical{border-left-color:var(--crit);background:#2A1A22;}
.name{font-family:'Newsreader',serif;font-size:1.3rem;}
.timer{font-family:'Newsreader',serif;font-size:1.7rem;text-align:right;
  font-variant-numeric:lining-nums tabular-nums;grid-row:span 2;align-self:center;}
.sub{color:var(--muted);font-size:.88rem;}
.row.warning .sub{color:var(--warn);}.row.critical .sub{color:#F08A85;}
.bar{grid-column:1/-1;height:3px;background:var(--line);margin-top:.5rem;}
.bar i{display:block;height:100%;background:var(--warn);}
.row.critical .bar i{background:var(--crit);}
@media (prefers-reduced-motion:reduce){.banner.critical{animation:none;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def get_engine() -> MonitorEngine:
    return MonitorEngine()


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
    if warn:
        return f'<div class="banner warning"><b>Attention needed.</b>{", ".join(warn)} flagged.</div>'
    return '<div class="banner ok"><b>All clear.</b>Every monitored parameter is within limits.</div>'


def panel_html(snap, cfg) -> str:
    sp, out = snap["speed"], []
    good = {"seatbelt": "Fastened", "speed": f"{sp:.0f} km/h, limit {cfg.speed_limit:.0f}",
            "drowsiness": "Eyes open", "phone": "No phone in hand"}
    bad = {"seatbelt": "Not fastened", "speed": f"{sp:.0f} km/h, over the {cfg.speed_limit:.0f} limit",
           "drowsiness": "Eyes closed", "phone": "Phone in use"}
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

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("### Controls")
    run = st.toggle("Monitoring active", key="run")
    cam = int(st.number_input("Camera index", 0, 10, cfg.camera_index))
    cfg.speed_mode = st.radio("Speed source", ["Simulated", "Manual"], horizontal=True)
    cfg.speed_limit = float(st.slider("Speed limit (km/h)", 20, 160, int(cfg.speed_limit)))
    if cfg.speed_mode == "Manual":
        cfg.manual_speed = float(st.slider("Current speed (km/h)", 0, 200, int(cfg.manual_speed)))
    cfg.ear_threshold = st.slider("Eye closure threshold", 0.10, 0.35, cfg.ear_threshold, 0.01)
    cfg.confirm_after = st.slider("Confirm an issue after (s)", 0.5, 5.0, cfg.confirm_after, 0.5)
    st.markdown("#### Critical alert after (seconds)")
    for p in PARAMS:
        cfg.critical_after[p] = float(st.number_input(TITLES[p], 3, 300, int(cfg.critical_after[p]), key=f"c_{p}"))
    cfg.log_interval = int(st.number_input("Report interval (minutes)", 1, 60, cfg.log_interval // 60)) * 60
    if st.button("Save report now", use_container_width=True):
        st.success(f"Saved {os.path.basename(engine.write_report())}")

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
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False), os.path.basename(pick), "text/csv")
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
                audio.audio(beep(), format="audio/wav", autoplay=True)
        time.sleep(0.03)
