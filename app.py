import streamlit as st

import auth
from theme import apply_theme

st.set_page_config(page_title="Driver Assurance", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
apply_theme()
auth.init_db()

if st.session_state.get("user"):
    pages = [st.Page("frontend.py", title="Monitor", icon=":material/shield:", default=True),
             st.Page("driver_profile.py", title="Driver profile", icon=":material/person:")]
    nav = st.navigation(pages)
else:
    nav = st.navigation([st.Page("login.py", title="Sign in")], position="hidden")
nav.run()
