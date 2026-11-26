# -*- coding: utf-8 -*-
"""frontend.py - DriveSaarthi live monitoring dashboard."""

import glob
import io
import os
import time
import wave
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import streamlit as st

import backend
from backend import PARAMS, TITLES, MonitorEngine
from notifier import IST

# ---------------------------------------------------------------------------
# Dashboard CSS
# ---------------------------------------------------------------------------
DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --accent:      #0EA5E9;
    --success:     #10B981;
    --warning:     #F59E0B;
    --danger:      #EF4444;
    --bg:          #030812;
    --surface:     #0A1628;
    --surface-2:   #0D1E34;
    --surface-3:   #122440;
    --border:      rgba(255,255,255,0.06);
    --border-hi:   rgba(14,165,233,0.3);
    --text:        #E2E8F0;
    --text-dim:    #CBD5E1;
    --text-muted:  #94A3B8;
    --mono:        'JetBrains Mono', monospace;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: var(--bg) !important;
    background-image:
        radial-gradient(ellipse 100% 40% at 50% 0%, rgba(14,165,233,0.07) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 100% 80%, rgba(16,185,129,0.04) 0%, transparent 50%) !important;
}

.main .block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 3rem !important;
    max-width: 1400px !important;
}

/* PAGE HEADER */
.ds-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    background: linear-gradient(135deg, rgba(14,165,233,0.06) 0%, rgba(16,185,129,0.03) 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    margin-bottom: 1.25rem;
}
.ds-header-left { display: flex; align-items: center; gap: 1rem; }
.ds-logo { font-size: 2rem; filter: drop-shadow(0 0 16px rgba(14,165,233,0.5)); }
.ds-title {
    font-size: 1.5rem; font-weight: 800; letter-spacing: -0.03em;
    background: linear-gradient(135deg, #E2E8F0 0%, #0EA5E9 60%, #10B981 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    line-height: 1.1;
}
.ds-subtitle {
    font-size: 0.75rem; color: #94A3B8;
    letter-spacing: 0.05em; text-transform: uppercase;
}
.ds-time {
    font-family: var(--mono); font-size: 0.8rem; color: #94A3B8;
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.35rem 0.75rem;
}

/* KPI STRIP */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}
.kpi-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); border-color: var(--border-hi); }
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    border-radius: 14px 14px 0 0;
}
.kpi-card.speed::before  { background: linear-gradient(90deg, #0EA5E9, #38BDF8); }
.kpi-card.eye::before    { background: linear-gradient(90deg, #10B981, #34D399); }
.kpi-card.fps::before    { background: linear-gradient(90deg, #8B5CF6, #A78BFA); }
.kpi-card.report::before { background: linear-gradient(90deg, #F59E0B, #FCD34D); }
.kpi-label {
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #94A3B8;
}
.kpi-value {
    font-family: var(--mono); font-size: 1.9rem; font-weight: 700;
    color: var(--text); line-height: 1.1; margin: 0.3rem 0 0.1rem;
}
.kpi-unit { font-size: 0.72rem; color: #94A3B8; }

/* STATUS BANNER */
.banner {
    display: flex; align-items: center; gap: 1rem;
    padding: 1rem 1.4rem; border-radius: 14px;
    margin-bottom: 1rem; font-size: 0.9rem; font-weight: 500;
    border: 1px solid transparent;
    animation: slideIn 0.3s ease;
}
@keyframes slideIn {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}
.banner-icon { font-size: 1.5rem; }
.banner.ok      { background: rgba(16,185,129,0.08);  border-color: rgba(16,185,129,0.2);  color: #6EE7B7 !important; }
.banner.warning { background: rgba(245,158,11,0.09);  border-color: rgba(245,158,11,0.25); color: #FCD34D !important; }
.banner.critical {
    background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3); color: #FCA5A5 !important;
    animation: pulseBanner 1.1s ease-in-out infinite;
}
@keyframes pulseBanner {
    0%,100% { box-shadow: 0 0 0 0   rgba(239,68,68,0.3); }
    50%     { box-shadow: 0 0 0 8px rgba(239,68,68,0);   }
}

/* PARAM CARDS */
.param-grid { display: flex; flex-direction: column; gap: 0.6rem; }
.pcard {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 0.85rem 1.1rem;
    overflow: hidden;
}
.pcard.ok       { border-left: 3px solid var(--success); }
.pcard.warning  { border-left: 3px solid var(--warning); }
.pcard.critical {
    border-left: 3px solid var(--danger);
    background: linear-gradient(135deg, rgba(239,68,68,0.07) 0%, var(--surface-2) 100%);
    animation: pulseCard 1.4s ease-in-out infinite;
}
@keyframes pulseCard {
    0%,100% { box-shadow: none; }
    50%     { box-shadow: 0 0 14px rgba(239,68,68,0.18); }
}
.pcard-top { display: flex; align-items: center; justify-content: space-between; }
.pcard-name {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #94A3B8;
    display: flex; align-items: center; gap: 0.4rem;
}
.pcard-timer { font-family: var(--mono); font-size: 1.3rem; font-weight: 700; color: var(--text); }
.pcard.ok       .pcard-timer { color: var(--success); }
.pcard.warning  .pcard-timer { color: var(--warning); }
.pcard.critical .pcard-timer { color: var(--danger); }
.pcard-sub { font-size: 0.75rem; color: #CBD5E1; margin-top: 0.25rem; }
.pcard-bar { height: 3px; background: var(--surface-3); border-radius: 99px; margin-top: 0.55rem; overflow: hidden; }
.pcard-bar i { display: block; height: 100%; border-radius: 99px; transition: width 0.5s ease; }
.pcard.ok       .pcard-bar i { background: var(--success); }
.pcard.warning  .pcard-bar i { background: var(--warning); }
.pcard.critical .pcard-bar i { background: var(--danger); }

/* STATUS DOT */
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.status-dot.ok       { background: var(--success); box-shadow: 0 0 6px var(--success); }
.status-dot.warning  { background: var(--warning); box-shadow: 0 0 6px var(--warning); }
.status-dot.critical { background: var(--danger);  box-shadow: 0 0 6px var(--danger);
    animation: dotPulse 1s ease-in-out infinite; }
@keyframes dotPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* VIDEO PAUSED STATE */
.video-paused {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 16px;
    min-height: 300px;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; gap: 0.5rem;
    color: #94A3B8; font-size: 0.9rem;
    margin-bottom: 0.75rem;
}

/* SECTION LABEL */
.section-label {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #94A3B8;
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 0.6rem;
}
.section-label::after { content: ''; flex: 1; height: 1px; background: var(--border); }

/* SIDEBAR */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"]::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--accent), var(--success));
}
[data-testid="stSidebar"] * { color: var(--text-dim) !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong,
[data-testid="stSidebar"] b { color: var(--text) !important; }
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
    background: rgba(14,165,233,0.12) !important;
    border-left: 3px solid var(--accent) !important;
    color: var(--accent) !important;
}
.driver-card {
    background: var(--surface-3); border: 1px solid var(--border-hi);
    border-radius: 12px; padding: 0.9rem 1rem; margin-bottom: 1rem;
}
.dc-name  { font-size: 0.9rem; font-weight: 700; color: var(--text) !important; }
.dc-plate {
    display: inline-block; margin-top: 0.3rem; font-family: var(--mono);
    font-size: 0.72rem; font-weight: 600;
    background: rgba(14,165,233,0.1); color: var(--accent) !important;
    border: 1px solid rgba(14,165,233,0.2); border-radius: 5px;
    padding: 0.12rem 0.45rem; letter-spacing: 0.08em;
}

/* BUTTONS */
.stButton > button {
    background: linear-gradient(135deg, #0EA5E9 0%, #0369A1 100%) !important;
    color: #FFFFFF !important; border: none !important; border-radius: 8px !important;
    font-weight: 700 !important; transition: all 0.2s !important;
    box-shadow: 0 2px 10px rgba(14,165,233,0.4) !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(14,165,233,0.4) !important;
}
.stButton > button p { color: #FFFFFF !important; font-weight: 700 !important; }

/* INPUTS */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    background: var(--surface-2) !important;
    border: 1px solid rgba(14,165,233,0.2) !important;
    border-radius: 8px !important; color: var(--text) !important;
}

/* TABS */
.stTabs [data-baseweb="tab-list"] { gap: 0.25rem; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 8px 8px 0 0;
    padding: 0.5rem 1rem; font-weight: 500; color: var(--text-muted) !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(14,165,233,0.08) !important;
    color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important;
}

/* DATAFRAMES */
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }

/* EXPANDERS */
[data-testid="stExpander"] {
    background: var(--surface-2); border: 1px solid var(--border) !important; border-radius: 12px !important;
}

/* ALERTS */
[data-testid="stAlert"] { border-radius: 10px; }

/* ── GLOBAL TEXT OVERRIDES ── */
/* Force all Streamlit-generated text to be legible on dark backgrounds */
p, span, div, li, td, th {
    color: var(--text-dim);
}
h1, h2, h3, h4, h5, h6 {
    color: var(--text) !important;
}
/* markdown paragraphs */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span {
    color: var(--text-dim) !important;
}
/* sidebar all text */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label {
    color: var(--text-dim) !important;
}
[data-testid="stSidebar"] strong,
[data-testid="stSidebar"] b {
    color: var(--text) !important;
}
/* form labels */
.stTextInput  label,
.stNumberInput label,
.stSelectbox  label,
.stSlider     label,
.stRadio      label,
.stCheckbox   label,
.stToggle     label {
    color: var(--text-dim) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
}
/* input text */
.stTextInput  > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox  > div > div,
.stTextArea   > div > div > textarea {
    background: var(--surface-2) !important;
    border: 1px solid rgba(14,165,233,0.2) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
    font-size: 0.88rem !important;
}
.stTextInput  > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(14,165,233,0.2) !important;
}
/* slider value */
[data-testid="stSlider"] p { color: var(--text-dim) !important; }
/* radio options */
.stRadio > div label p { color: var(--text-dim) !important; }
/* toggle label */
.stToggle p { color: var(--text-dim) !important; }
/* caption / small text */
[data-testid="stCaptionContainer"] p { color: var(--text-muted) !important; }
/* selectbox text */
.stSelectbox [data-baseweb="select"] [data-testid="stMarkdownContainer"] p {
    color: var(--text) !important;
}
/* button — solid blue, white text, no ambiguity */
.stButton > button,
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #0EA5E9 0%, #0369A1 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.02em !important;
    text-shadow: none !important;
    box-shadow: 0 2px 10px rgba(14,165,233,0.4) !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background: linear-gradient(135deg, #38BDF8 0%, #0EA5E9 100%) !important;
    color: #FFFFFF !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 18px rgba(14,165,233,0.55) !important;
}
.stButton > button p,
.stFormSubmitButton > button p {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}
/* tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem !important;
    border-bottom: 1px solid var(--border) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
}
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span {
    color: var(--text-muted) !important;
    font-weight: 600 !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(14,165,233,0.09) !important;
    color: #38BDF8 !important;
    border-bottom: 2px solid var(--accent) !important;
}
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] span {
    color: #38BDF8 !important;
}
/* alerts */
[data-testid="stAlert"] { border-radius: 10px !important; }
[data-testid="stAlert"] p { color: var(--text) !important; }
/* dataframes */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
}
/* expanders */
[data-testid="stExpander"] {
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary p {
    color: var(--text-dim) !important;
    font-weight: 500 !important;
}
/* HIDE CHROME */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
/* SCROLLBAR */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--surface-3); border-radius: 4px; }
</style>
"""

st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PARAM_ICONS = {
    "seatbelt":   "🔒",
    "speed":      "🚀",
    "drowsiness": "👁️",
    "phone":      "📵",
    "camera":     "📷",
}

PIE_COLORS = {
    "Seatbelt":     "#0EA5E9",
    "Speed":        "#EF4444",
    "Drowsiness":   "#F59E0B",
    "Mobile phone": "#8B5CF6",
    "Camera feed":  "#10B981",
}

# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def _make_engine() -> MonitorEngine:
    return MonitorEngine()


def get_engine() -> MonitorEngine:
    e = _make_engine()
    stale = (
        getattr(e, "version", 0) != getattr(backend, "BACKEND_VERSION", 0)
        or not hasattr(e.cfg, "min_speed_checks")
    )
    if stale:
        try:
            e.stop(flush=False)
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


# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------
def safety_score(snap) -> int:
    """0-100: critical = -20 each, warning = -10 each."""
    score = 100
    for p in PARAMS:
        lvl = snap["params"][p]["level"]
        if lvl == "critical":
            score -= 20
        elif lvl == "warning":
            score -= 10
    return max(0, score)


def make_donut(score: int) -> plt.Figure:
    """Coloured donut for the live safety score."""
    color = "#10B981" if score >= 80 else ("#F59E0B" if score >= 50 else "#EF4444")
    fig, ax = plt.subplots(figsize=(3.0, 3.0), facecolor="none")
    ax.set_facecolor("none")
    ax.pie(
        [score, 100 - score],
        colors=[color, "#122440"],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.28, edgecolor="none", linewidth=0),
    )
    ax.text(0, 0.08, str(score), ha="center", va="center",
            fontsize=26, fontweight="bold", color=color, fontfamily="monospace")
    ax.text(0, -0.3, "Safety Score", ha="center", va="center",
            fontsize=7, color="#64748B", fontfamily="sans-serif")
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    fig.tight_layout(pad=0)
    return fig


def make_session_pie(snap) -> "plt.Figure | None":
    """Donut of cumulative issue seconds per parameter this session."""
    data = {
        TITLES[p]: snap["params"][p]["total"]
        for p in PARAMS
        if snap["params"][p]["total"] > 0.5
    }
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(3.2, 3.2), facecolor="none")
    ax.set_facecolor("none")
    colors = [PIE_COLORS.get(k, "#64748B") for k in data]
    _, _, autotexts = ax.pie(
        list(data.values()),
        labels=None,
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct="%1.0f%%",
        pctdistance=0.72,
        wedgeprops=dict(edgecolor="#030812", linewidth=2.5, width=0.55),
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(8)
        t.set_fontweight("bold")
    patches = [mpatches.Patch(color=c, label=k) for k, c in zip(data.keys(), colors)]
    ax.legend(patches, data.keys(), loc="lower center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, fontsize=6.5, frameon=False, labelcolor="#94A3B8",
              handlelength=1, handleheight=0.8)
    ax.set_title("Session violations", fontsize=7.5, color="#64748B", pad=6)
    fig.tight_layout(pad=0.3)
    return fig


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------
def banner_html(snap) -> str:
    ps   = snap["params"]
    crit = [TITLES[p] for p in PARAMS if ps[p]["level"] == "critical"]
    warn = [TITLES[p] for p in PARAMS if ps[p]["level"] == "warning"]
    if not snap["camera_ok"]:
        return ('<div class="banner warning"><span class="banner-icon">📷</span>'
                '<div><b>Camera unavailable.</b> Check the camera index in the sidebar.</div></div>')
    if crit:
        return (f'<div class="banner critical"><span class="banner-icon">🚨</span>'
                f'<div><b>Critical alert.</b> Unresolved: {", ".join(crit)}. Act now.</div></div>')
    if snap["calibrating"]:
        return ('<div class="banner warning"><span class="banner-icon">🎯</span>'
                '<div><b>Calibrating.</b> Look straight ahead for five seconds.</div></div>')
    if warn:
        return (f'<div class="banner warning"><span class="banner-icon">⚠️</span>'
                f'<div><b>Attention needed.</b> {", ".join(warn)} flagged.</div></div>')
    return ('<div class="banner ok"><span class="banner-icon">✅</span>'
            '<div><b>All clear.</b> Every parameter is within limits.</div></div>')


def kpi_strip_html(snap) -> str:
    ear = "n/a" if snap["ear"] is None else f"{snap['ear']:.2f}"
    return (
        '<div class="kpi-strip">'
        f'<div class="kpi-card speed">'
        f'<div class="kpi-label">Speed</div>'
        f'<div class="kpi-value">{snap["speed"]:.0f}</div>'
        f'<div class="kpi-unit">km/h</div></div>'
        f'<div class="kpi-card eye">'
        f'<div class="kpi-label">Eye Openness</div>'
        f'<div class="kpi-value">{ear}</div>'
        f'<div class="kpi-unit">EAR ratio</div></div>'
        f'<div class="kpi-card fps">'
        f'<div class="kpi-label">Analysis Rate</div>'
        f'<div class="kpi-value">{snap["fps"]:.0f}</div>'
        f'<div class="kpi-unit">frames/sec</div></div>'
        f'<div class="kpi-card report">'
        f'<div class="kpi-label">Next Report</div>'
        f'<div class="kpi-value">{mmss(snap["next_report"])}</div>'
        f'<div class="kpi-unit">mm:ss</div></div>'
        '</div>'
    )


def param_cards_html(snap, cfg) -> str:
    sp = snap["speed"]
    good = {
        "seatbelt":   "Fastened",
        "speed":      f"{sp:.0f} km/h - limit {cfg.speed_limit:.0f}",
        "drowsiness": "Eyes open",
        "phone":      "No phone in hand",
        "camera":     "Feed live",
    }
    bad = {
        "seatbelt":   "Not fastened",
        "speed":      f"{sp:.0f} km/h - over {cfg.speed_limit:.0f} limit",
        "drowsiness": "Eyes closed / drooping",
        "phone":      "Phone in use",
        "camera":     "Feed lost or blocked",
    }
    out = ['<div class="param-grid">']
    for p in PARAMS:
        s   = snap["params"][p]
        lvl = s["level"]
        icon = PARAM_ICONS[p]
        if lvl == "ok":
            sub = ("No driver in frame"
                   if not snap["driver"] and p in ("seatbelt", "drowsiness")
                   else good[p])
        elif lvl == "warning":
            sub = f"{bad[p]} - critical in {max(0, s['limit'] - s['duration']):.0f}s"
        else:
            sub = f"{bad[p]} - critical alert raised"
        pct   = min(100, 100 * s["duration"] / max(0.01, s["limit"])) if lvl != "ok" else 0
        timer = mmss(s["duration"]) if lvl != "ok" else "00:00"
        out.append(
            f'<div class="pcard {lvl}">'
            f'<div class="pcard-top">'
            f'<div class="pcard-name">'
            f'<span class="status-dot {lvl}"></span>{icon} {TITLES[p]}'
            f'</div>'
            f'<div class="pcard-timer">{timer}</div>'
            f'</div>'
            f'<div class="pcard-sub">{sub}</div>'
            f'<div class="pcard-bar"><i style="width:{pct}%"></i></div>'
            f'</div>'
        )
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Engine & user
# ---------------------------------------------------------------------------
engine = get_engine()
cfg    = engine.cfg
user   = st.session_state.get("user")
if not user:
    st.error("Please start the app with `streamlit run app.py` and sign in.")
    st.stop()
engine.set_driver(user)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    plate_label = user["vehicle_plate"] or "No plate set"
    st.markdown(
        f'<div class="driver-card">'
        f'<div class="dc-name">👤 &nbsp;{user["full_name"]}</div>'
        f'<span class="dc-plate">🚗 &nbsp;{plate_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button("Sign out", use_container_width=True):
        engine.stop()
        engine.set_driver(None)
        st.session_state.pop("user", None)
        st.rerun()

    st.markdown("---")
    st.markdown("**Controls**")
    run = st.toggle("Monitoring active", key="run")
    cam = int(st.number_input("Camera index", 0, 10, cfg.camera_index))

    st.markdown("**Speed**")
    cfg.speed_mode  = st.radio("Speed source", ["Simulated", "Manual"], horizontal=True)
    cfg.speed_limit = float(st.slider("Speed limit (km/h)", 20, 160, int(cfg.speed_limit)))
    if cfg.speed_mode == "Manual":
        cfg.manual_speed = float(st.slider("Current speed (km/h)", 0, 200, int(cfg.manual_speed)))

    st.markdown("**Drowsiness**")
    cfg.ear_threshold = st.slider("Eye closure threshold", 0.10, 0.35, cfg.ear_threshold, 0.01)

    st.markdown("**Timing**")
    cfg.confirm_after    = st.slider("Confirm issue after (s)", 0.5, 5.0, cfg.confirm_after, 0.5)
    cfg.min_speed_checks = float(st.number_input(
        "Seatbelt & phone checks above (km/h)", 0, 60, int(cfg.min_speed_checks)))
    cfg.realert_every    = float(st.number_input(
        "Repeat critical alert every (s)", 3, 120, int(cfg.realert_every)))

    with st.expander("Critical thresholds (s)"):
        for p in PARAMS:
            cfg.critical_after[p] = float(st.number_input(
                TITLES[p], 3, 300, int(cfg.critical_after[p]), key=f"c_{p}"))

    cfg.log_interval = int(st.number_input(
        "Report interval (min)", 1, 60, cfg.log_interval // 60)) * 60

    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("Save report", use_container_width=True):
        st.success(f"Saved {os.path.basename(engine.write_report())}")
    if c2.button("Calibrate eyes", use_container_width=True, disabled=not run):
        engine.calibrate()

# ---------------------------------------------------------------------------
# Camera / engine start-stop
# ---------------------------------------------------------------------------
if cam != cfg.camera_index:
    cfg.camera_index = cam
    if engine.running:
        engine.stop(flush=False)
        engine.start()
if run and not engine.running:
    with st.spinner("Loading models and opening camera..."):
        engine.start()
elif not run and engine.running:
    engine.stop()

_m = engine.snapshot()
if run and not (_m["models"]["face"] and _m["models"]["phone"]):
    st.sidebar.warning("A model failed to load - some checks are off. " + _m["error"])
elif run:
    st.sidebar.caption(f"Seatbelt check: {_m['models']['seatbelt']}")

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
now_str = datetime.now(IST).strftime("%d %b %Y - %I:%M %p IST")
st.markdown(
    f'<div class="ds-header">'
    f'<div class="ds-header-left">'
    f'<span class="ds-logo">🛡️</span>'
    f'<div>'
    f'<div class="ds-title">DriveSaarthi</div>'
    f'<div class="ds-subtitle">Live Safety Monitor - {user["full_name"]}</div>'
    f'</div></div>'
    f'<div class="ds-time">{now_str}</div>'
    f'</div>',
    unsafe_allow_html=True,
)

kpi_ph    = st.empty()
banner_ph = st.empty()

# ---------------------------------------------------------------------------
# Main 3-column layout
# ---------------------------------------------------------------------------
col_vid, col_params, col_charts = st.columns([1.6, 1.1, 1.0], gap="medium")

with col_vid:
    st.markdown('<div class="section-label">📹 Camera feed</div>', unsafe_allow_html=True)
    video_ph = st.empty()

with col_params:
    st.markdown('<div class="section-label">🔍 Parameter status</div>', unsafe_allow_html=True)
    panel_ph = st.empty()

with col_charts:
    st.markdown('<div class="section-label">📊 Analytics</div>', unsafe_allow_html=True)
    donut_ph = st.empty()
    pie_ph   = st.empty()

audio_ph = st.empty()

# ---------------------------------------------------------------------------
# Tabs: event log / saved reports
# ---------------------------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
tab_log, tab_rep = st.tabs(["📋  Event log", "📊  Saved reports"])
log_ph = tab_log.empty()

with tab_rep:
    files = sorted(glob.glob(os.path.join(cfg.log_dir, "report_*.csv")), reverse=True)
    if files:
        pick = st.selectbox("Report", files,
                            format_func=os.path.basename,
                            label_visibility="collapsed")
        df  = pd.read_csv(pick)
        png = pick[:-4] + ".png"
        rc1, rc2 = st.columns([1, 1.4], gap="large")
        if os.path.exists(png):
            rc1.image(png, caption="Issue time share", use_container_width=True)

        rep_seconds = {}
        if "parameter" in df.columns and "sustained_seconds" in df.columns:
            for _, row in df.iterrows():
                rep_seconds[str(row["parameter"])] = float(row["sustained_seconds"])

        if rep_seconds:
            items = [(k, v) for k, v in rep_seconds.items() if v > 0]
            if items:
                rfig, rax = plt.subplots(figsize=(4, 3.5), facecolor="none")
                rax.set_facecolor("none")
                rcolors = [PIE_COLORS.get(k, "#64748B") for k, _ in items]
                rax.pie(
                    [v for _, v in items],
                    labels=[f"{k}\n{v:.0f}s" for k, v in items],
                    colors=rcolors,
                    startangle=90, counterclock=False,
                    autopct="%1.0f%%", pctdistance=0.68,
                    wedgeprops=dict(edgecolor="#030812", linewidth=2.5),
                    textprops=dict(color="#94A3B8", fontsize=8),
                )
                for a in rax.texts[1::2]:
                    a.set_color("white")
                    a.set_fontweight("bold")
                rax.set_title("Issue time breakdown", color="#64748B", fontsize=9, pad=10)
                rfig.tight_layout(pad=0.3)
                rc1.pyplot(rfig, use_container_width=True)
                plt.close(rfig)

        rc2.dataframe(
            df.drop(columns=["driver", "window_start", "window_end"], errors="ignore"),
            hide_index=True, use_container_width=True,
        )
        rc2.download_button("Download CSV",
                            df.to_csv(index=False), os.path.basename(pick), "text/csv")
        if os.path.exists(png):
            rc2.download_button("Download chart",
                                open(png, "rb").read(), os.path.basename(png), "image/png")
    else:
        st.caption(
            f"No reports yet. One is saved every {cfg.log_interval // 60} min while monitoring runs."
        )


# ---------------------------------------------------------------------------
# Render helper
# ---------------------------------------------------------------------------
def render(snap: dict, slow: bool) -> None:
    kpi_ph.markdown(kpi_strip_html(snap), unsafe_allow_html=True)
    banner_ph.markdown(banner_html(snap), unsafe_allow_html=True)
    panel_ph.markdown(param_cards_html(snap, cfg), unsafe_allow_html=True)

    if slow:
        score = safety_score(snap)
        fig_d = make_donut(score)
        donut_ph.pyplot(fig_d, use_container_width=True)
        plt.close(fig_d)

        fig_p = make_session_pie(snap)
        if fig_p:
            pie_ph.pyplot(fig_p, use_container_width=True)
            plt.close(fig_p)
        else:
            pie_ph.markdown(
                '<div style="background:rgba(16,185,129,0.05);border:1px solid rgba(16,185,129,0.12);'
                'border-radius:12px;padding:1.2rem;text-align:center;color:#94A3B8;font-size:0.8rem;">'
                '✅ No violations recorded this session</div>',
                unsafe_allow_html=True,
            )

        rows = snap["events"][:15]
        if rows:
            log_ph.dataframe(
                pd.DataFrame(rows, columns=["Time", "Parameter", "Event"]),
                hide_index=True, use_container_width=True,
            )
        else:
            log_ph.caption("No events yet.")


# ---------------------------------------------------------------------------
# Initial render + live loop
# ---------------------------------------------------------------------------
snap = engine.snapshot()
render(snap, True)

if not run:
    video_ph.markdown(
        '<div class="video-paused">'
        '<span style="font-size:2.5rem">⏸️</span>'
        '<span>Monitoring is paused</span>'
        '<span style="font-size:0.75rem;color:#94A3B8">'
        'Turn on <b>Monitoring active</b> in the sidebar</span>'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    last_seq, last_ui, last_slow = snap["critical_seq"], 0.0, 0.0
    while True:
        frame = engine.frame()
        if frame is not None:
            video_ph.image(frame, channels="BGR", output_format="JPEG", use_container_width=True)
        now = time.time()
        if now - last_ui > 0.25:
            snap = engine.snapshot()
            render(snap, now - last_slow > 1.5)
            last_ui = now
            if now - last_slow > 1.5:
                last_slow = now
            if snap["critical_seq"] != last_seq:
                last_seq = snap["critical_seq"]
                audio_ph.audio(beep(), format="audio/wav", autoplay=True,
                               alt=f"Alert beep {last_seq}")
        time.sleep(0.03)
