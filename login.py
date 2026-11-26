# -*- coding: utf-8 -*-
"""Sign-in and driver registration page."""
import streamlit as st
import streamlit.components.v1 as components
import auth

# ── Hide sidebar ──────────────────────────────────────────────────────────────
st.markdown(
    "<style>"
    "[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}"
    "</style>",
    unsafe_allow_html=True,
)

# ── Global page CSS (Streamlit-level: app bg, inputs, buttons, tabs) ─────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: #030812 !important;
    min-height: 100vh;
}
.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
}

/* remove gap between columns */
[data-testid="column"] { padding: 0 !important; }

/* right column dark background */
[data-testid="column"]:last-child {
    background: #060D1A;
    min-height: 100vh;
    padding: 2.5rem 2rem !important;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* welcome card */
.rp-card {
    background: rgba(10,22,40,0.9);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 1.8rem 1.6rem 1rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 20px 56px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
}
.rp-title    { font-size: 1.3rem; font-weight: 700; color: #E2E8F0; margin-bottom: 0.2rem; }
.rp-subtitle { font-size: 0.8rem; color: #94A3B8; }

/* auth note */
.auth-note {
    font-size: 0.78rem; color: #CBD5E1 !important;
    background: rgba(245,158,11,0.07);
    border: 1px solid rgba(245,158,11,0.2);
    border-radius: 8px; padding: 0.55rem 0.8rem;
    margin-bottom: 0.85rem; line-height: 1.55;
}

/* footer */
.rp-footer { font-size: 0.7rem; color: #475569; text-align: center; margin-top: 1rem; }

/* tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.2rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1rem !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    color: #94A3B8 !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(14,165,233,0.09) !important;
    color: #0EA5E9 !important;
    border-bottom: 2px solid #0EA5E9 !important;
}

/* ── ALL STREAMLIT TEXT: force light colour on dark bg ── */
p, span, div, label, h1, h2, h3, h4, h5, h6,
[class*="st-"], [data-testid] {
    color: #CBD5E1;
}

/* form labels */
.stTextInput  label,
.stNumberInput label,
.stSelectbox  label,
.stTextArea   label,
.stCheckbox   label,
.stRadio      label {
    color: #94A3B8 !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em !important;
}

/* inputs */
.stTextInput  > div > div > input,
.stNumberInput > div > div > input,
.stTextArea   > div > div > textarea {
    background: #0B1A2E !important;
    border: 1px solid rgba(14,165,233,0.25) !important;
    border-radius: 8px !important;
    color: #E2E8F0 !important;
    font-size: 0.9rem !important;
}
.stTextInput  > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea   > div > div > textarea:focus {
    border-color: #0EA5E9 !important;
    box-shadow: 0 0 0 3px rgba(14,165,233,0.2) !important;
    outline: none !important;
}
/* placeholder */
.stTextInput  > div > div > input::placeholder,
.stNumberInput > div > div > input::placeholder {
    color: #475569 !important;
}

/* form-submit button — most specific possible selector */
.stFormSubmitButton > button,
.stButton > button {
    background: linear-gradient(135deg, #0EA5E9 0%, #0369A1 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.6rem 1rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 8px rgba(14,165,233,0.35) !important;
    text-shadow: none !important;
}
.stFormSubmitButton > button:hover,
.stButton > button:hover {
    background: linear-gradient(135deg, #38BDF8 0%, #0EA5E9 100%) !important;
    color: #FFFFFF !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(14,165,233,0.5) !important;
}
.stFormSubmitButton > button p,
.stButton > button p {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

/* tab text */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.2rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1rem !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    color: #64748B !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span {
    color: #64748B !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(14,165,233,0.1) !important;
    color: #38BDF8 !important;
    border-bottom: 2px solid #0EA5E9 !important;
}
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] span {
    color: #38BDF8 !important;
}

/* error/info alerts */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    color: #E2E8F0 !important;
}
[data-testid="stAlert"] p { color: #E2E8F0 !important; }

#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Two-column layout ─────────────────────────────────────────────────────────
col_left, col_right = st.columns([1.1, 0.9], gap="small")

# ── LEFT: rendered via st.components.v1.html — bypasses Streamlit's sanitizer ─
# This is the ONLY reliable way to render nested <div> HTML in Streamlit.
with col_left:
    components.html("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@500&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Inter', sans-serif;
    background:
        radial-gradient(ellipse 100% 80% at 20% 10%, rgba(14,165,233,0.18) 0%, transparent 55%),
        radial-gradient(ellipse 80% 60% at 80% 90%, rgba(16,185,129,0.12) 0%, transparent 50%),
        linear-gradient(160deg, #060f20 0%, #030812 60%, #04101e 100%);
    min-height: 100vh;
    padding: 3rem 2.5rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    border-right: 1px solid rgba(14,165,233,0.12);
    position: relative;
    overflow: hidden;
    color: #E2E8F0;
}

.orb {
    position: fixed;
    border-radius: 50%;
    filter: blur(70px);
    pointer-events: none;
    animation: drift 9s ease-in-out infinite alternate;
}
.orb-1 { width: 300px; height: 300px; background: rgba(14,165,233,0.08); top: -80px; left: -80px; }
.orb-2 { width: 220px; height: 220px; background: rgba(16,185,129,0.06); bottom: 40px; right: -50px; animation-duration: 11s; animation-direction: alternate-reverse; }
@keyframes drift {
    from { transform: translate(0,0) scale(1); }
    to   { transform: translate(18px,25px) scale(1.08); }
}

.logo {
    font-size: 3rem; line-height: 1; margin-bottom: 0.5rem;
    display: inline-block;
    animation: logoPulse 3s ease-in-out infinite;
    filter: drop-shadow(0 0 22px rgba(14,165,233,0.55));
}
@keyframes logoPulse {
    0%,100% { filter: drop-shadow(0 0 22px rgba(14,165,233,0.5)); }
    50%      { filter: drop-shadow(0 0 42px rgba(14,165,233,0.85)); }
}

.brand-name {
    font-size: 2.4rem; font-weight: 900; letter-spacing: -0.04em; line-height: 1.1;
    background: linear-gradient(135deg, #E2E8F0 0%, #0EA5E9 55%, #10B981 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin: 0 0 0.3rem;
}
.brand-tag {
    font-size: 0.75rem; font-weight: 500; color: #64748B;
    letter-spacing: 0.1em; text-transform: uppercase;
}
.divider {
    width: 52px; height: 3px;
    background: linear-gradient(90deg, #0EA5E9, #10B981);
    border-radius: 99px; margin: 1.3rem 0;
}
.desc { font-size: 0.9rem; color: #94A3B8; line-height: 1.75; max-width: 380px; }

.features { display: flex; flex-direction: column; gap: 0.65rem; margin-top: 1.8rem; }
.feat {
    display: flex; align-items: center; gap: 0.85rem;
    padding: 0.65rem 0.9rem;
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.055);
    border-radius: 10px;
    transition: border-color 0.2s, background 0.2s;
}
.feat:hover { background: rgba(14,165,233,0.06); border-color: rgba(14,165,233,0.2); }
.feat-icon {
    font-size: 1.2rem; flex-shrink: 0;
    width: 36px; height: 36px;
    display: flex; align-items: center; justify-content: center;
    background: rgba(14,165,233,0.09); border-radius: 8px;
}
.feat-title { font-size: 0.82rem; font-weight: 600; color: #CBD5E1; display: block; }
.feat-sub   { font-size: 0.72rem; color: #64748B; }

.stats {
    display: flex; gap: 2rem;
    padding-top: 1.8rem;
    border-top: 1px solid rgba(255,255,255,0.045);
    margin-top: 1.5rem;
}
.stat-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.4rem; font-weight: 700; color: #0EA5E9; line-height: 1;
}
.stat-lbl { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: #64748B; margin-top: 0.2rem; }
</style>
</head>
<body>
  <div class="orb orb-1"></div>
  <div class="orb orb-2"></div>

  <div>
    <div class="logo">&#x1F6E1;&#xFE0F;</div>
    <div class="brand-name">DriveSaarthi</div>
    <div class="brand-tag">Driver Safety Evaluation System</div>
    <div class="divider"></div>
    <p class="desc">Real-time AI cabin monitoring — detecting fatigue, phone use, seatbelt compliance and over-speed in one unified dashboard.</p>

    <div class="features">
      <div class="feat">
        <div class="feat-icon">&#x1F441;&#xFE0F;</div>
        <div>
          <span class="feat-title">Drowsiness Detection</span>
          <span class="feat-sub">Eye-aspect ratio &amp; PERCLOS via MediaPipe</span>
        </div>
      </div>
      <div class="feat">
        <div class="feat-icon">&#x1F4F5;</div>
        <div>
          <span class="feat-title">Phone Distraction</span>
          <span class="feat-sub">YOLOv8 detection with driver-proximity filter</span>
        </div>
      </div>
      <div class="feat">
        <div class="feat-icon">&#x1F512;</div>
        <div>
          <span class="feat-title">Seatbelt Compliance</span>
          <span class="feat-sub">Hough-line heuristic &amp; custom model voting</span>
        </div>
      </div>
      <div class="feat">
        <div class="feat-icon">&#x1F6A8;</div>
        <div>
          <span class="feat-title">Progressive Alerts</span>
          <span class="feat-sub">Audio beep &#x2192; voice warning;</span>
        </div>
      </div>
    </div>
  </div>

  <div class="stats">
    <div>
      <div class="stat-num">5</div>
      <div class="stat-lbl">Parameters<br>monitored</div>
    </div>
    <div>
      <div class="stat-num">15 FPS</div>
      <div class="stat-lbl">Analysis<br>rate</div>
    </div>
    <div>
      <div class="stat-num">3-tier</div>
      <div class="stat-lbl">Alert<br>escalation</div>
    </div>
  </div>
</body>
</html>
""", height=820, scrolling=False)

# ── RIGHT: pure Streamlit widgets, zero raw HTML divs ─────────────────────────
with col_right:
    st.markdown(
        '<div class="rp-card">'
        '<p class="rp-title">Welcome back</p>'
        '<p class="rp-subtitle">Sign in to your DriveSaarthi account</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    tab_in, tab_new = st.tabs(["🔑  Sign in", "✨  Create account"])

    # ── Sign in ───────────────────────────────────────────────────────────────
    with tab_in:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("signin"):
            u = st.text_input("Username", placeholder="your_username")
            p = st.text_input("Password", type="password", placeholder="••••••••")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Sign in  →", use_container_width=True):
                user, msg = auth.login(u, p)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                st.error(msg)

    # ── Register ──────────────────────────────────────────────────────────────
    with tab_new:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("register"):
            a, b = st.columns(2)
            name  = a.text_input("Full name",        placeholder="Ravi Kumar")
            uname = b.text_input("Username",          placeholder="ravi_k")
            pw    = a.text_input("Password",   type="password", placeholder="••••••••")
            pw2   = b.text_input("Confirm",    type="password", placeholder="••••••••")
            plate = a.text_input("Vehicle reg.",      placeholder="DL 01 AB 1234")
            lic   = b.text_input("Licence no.",       placeholder="DL-1420110012345")
            email = st.text_input("Email (optional)", placeholder="ravi@example.com")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Create account  →", use_container_width=True):
                if pw != pw2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = auth.register(name, uname, pw, "", "", plate, lic, email)
                    if ok:
                        user, _ = auth.login(uname, pw)
                        st.session_state["user"] = user
                        st.rerun()
                    st.error(msg)

    st.markdown(
        '<p class="rp-footer">&#169; 2026 DriveSaarthi &middot; AI-powered driver safety</p>',
        unsafe_allow_html=True,
    )
