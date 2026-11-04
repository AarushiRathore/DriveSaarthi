"""
theme.py – Visual theme for Driver Assurance.

Call apply_theme() once near the top of every page (after st.set_page_config).
"""

import streamlit as st


def apply_theme() -> None:
    """Inject custom CSS for a clean, professional Driver Assurance look."""
    st.markdown(
        """
        <style>
        /* ---------- Global ---------- */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }

        .stApp {
            background-color: #F8FAFC;
            color: #0F172A;
        }

        /* ---------- Main content area ---------- */
        .main .block-container {
            padding-top: 1.75rem;
            padding-bottom: 2.5rem;
            max-width: 1200px;
        }

        /* ---------- Sidebar ---------- */
        [data-testid="stSidebar"] {
            background-color: #0F172A;
            border-right: 1px solid #1E293B;
        }

        [data-testid="stSidebar"] * {
            color: #E2E8F0 !important;
        }

        [data-testid="stSidebar"] .stMarkdown a {
            color: #94A3B8 !important;
        }

        [data-testid="stSidebar"] .stMarkdown a:hover {
            color: #0D9488 !important;
        }

        [data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
            background-color: rgba(13, 148, 136, 0.18);
            border-left: 3px solid #0D9488;
        }

        /* ---------- Headers ---------- */
        h1 {
            font-weight: 700 !important;
            letter-spacing: -0.025em;
            color: #0F172A !important;
            margin-bottom: 0.5rem !important;
        }

        h2, h3 {
            font-weight: 600 !important;
            color: #0F172A !important;
        }

        /* ---------- Metrics ---------- */
        [data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 1rem 1.25rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }

        [data-testid="stMetricValue"] {
            font-weight: 700 !important;
            color: #0F172A !important;
        }

        /* ---------- Buttons ---------- */
        .stButton > button {
            background-color: #0D9488;
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 500;
            padding: 0.5rem 1.25rem;
            transition: background-color 0.15s ease, box-shadow 0.15s ease;
            box-shadow: 0 1px 2px rgba(13, 148, 136, 0.25);
        }

        .stButton > button:hover {
            background-color: #0F766E;
            color: white;
            box-shadow: 0 2px 6px rgba(13, 148, 136, 0.35);
        }

        .stButton > button:focus {
            box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.35);
        }

        .stButton > button[kind="secondary"] {
            background-color: transparent;
            color: #0D9488;
            border: 1.5px solid #0D9488;
            box-shadow: none;
        }

        .stButton > button[kind="secondary"]:hover {
            background-color: rgba(13, 148, 136, 0.08);
            color: #0F766E;
            border-color: #0F766E;
        }

        /* ---------- Inputs ---------- */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stNumberInput > div > div > input,
        .stTextArea > div > div > textarea {
            border-radius: 8px !important;
            border-color: #E2E8F0 !important;
        }

        .stTextInput > div > div > input:focus,
        .stSelectbox > div > div:focus-within,
        .stNumberInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: #0D9488 !important;
            box-shadow: 0 0 0 2px rgba(13, 148, 136, 0.2) !important;
        }

        /* ---------- Expanders ---------- */
        [data-testid="stExpander"] {
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            background-color: #FFFFFF;
            overflow: hidden;
        }

        /* ---------- Dataframes ---------- */
        [data-testid="stDataFrame"] {
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            overflow: hidden;
        }

        /* ---------- Tabs ---------- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
            border-bottom: 1px solid #E2E8F0;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 0.5rem 1rem;
            font-weight: 500;
        }

        .stTabs [aria-selected="true"] {
            background-color: rgba(13, 148, 136, 0.08);
            color: #0D9488 !important;
            border-bottom: 2px solid #0D9488;
        }

        /* ---------- Alerts ---------- */
        [data-testid="stAlert"] {
            border-radius: 10px;
            border: none;
        }

        /* ---------- Dividers ---------- */
        hr {
            border-color: #E2E8F0;
            margin: 1.5rem 0;
        }

        /* ---------- Hide default Streamlit chrome ---------- */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* ---------- Scrollbar ---------- */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: #CBD5E1;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #94A3B8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
