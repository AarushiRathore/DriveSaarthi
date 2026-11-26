"""
theme.py – Minimal shared theme for DriveSaarthi.

Each page (login.py, frontend.py, driver_profile.py) injects its own
full CSS.  apply_theme() just loads the shared Inter/Mono fonts and
overrides Streamlit's native widget colour tokens so they don't clash
with the dark palette.
"""

import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         Roboto, Oxygen, Ubuntu, sans-serif;
        }

        /* Global dark background fallback */
        .stApp { background: #030812 !important; color: #E2E8F0; }

        /* Inputs dark */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stSelectbox > div > div {
            background: #0D1E34 !important;
            border: 1px solid rgba(255,255,255,0.07) !important;
            border-radius: 8px !important;
            color: #E2E8F0 !important;
        }
        .stTextInput > div > div > input:focus,
        .stNumberInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: #0EA5E9 !important;
            box-shadow: 0 0 0 3px rgba(14,165,233,0.2) !important;
        }

        /* Buttons */
        .stButton > button {
            background: linear-gradient(135deg, #0EA5E9, #0284C7) !important;
            color: #fff !important; border: none !important;
            border-radius: 8px !important; font-weight: 600 !important;
            transition: all 0.2s !important;
        }
        .stButton > button:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 14px rgba(14,165,233,0.4) !important;
        }

        /* Sliders */
        [data-testid="stSlider"] > div > div > div > div { background: #0EA5E9 !important; }

        /* Toggle */
        [data-testid="stToggle"] span[data-checked="true"] { background: #10B981 !important; }

        /* Radio */
        [data-testid="stRadio"] label { color: #94A3B8 !important; }

        /* Metrics */
        [data-testid="stMetric"] {
            background: #0D1E34; border: 1px solid rgba(255,255,255,0.07);
            border-radius: 12px; padding: 1rem 1.2rem;
        }
        [data-testid="stMetricLabel"] > div {
            color: #64748B !important; font-size: 0.72rem !important;
            font-weight: 600 !important; letter-spacing: 0.06em !important;
            text-transform: uppercase !important;
        }
        [data-testid="stMetricValue"] { font-weight: 800 !important; color: #E2E8F0 !important; }

        /* Expanders */
        [data-testid="stExpander"] {
            background: #0D1E34 !important;
            border: 1px solid rgba(255,255,255,0.07) !important;
            border-radius: 12px !important;
        }

        /* Dataframes */
        [data-testid="stDataFrame"] {
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 12px; overflow: hidden;
        }

        /* Alerts */
        [data-testid="stAlert"] { border-radius: 10px; }

        /* Dividers */
        hr { border-color: rgba(255,255,255,0.07) !important; margin: 1.25rem 0; }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #122440; border-radius: 4px; }

        /* Spinner */
        [data-testid="stSpinner"] > div { border-top-color: #0EA5E9 !important; }

        /* Hide chrome */
        #MainMenu { visibility: hidden; }
        footer    { visibility: hidden; }
        header    { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )
