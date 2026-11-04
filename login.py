"""Sign-in and driver registration page."""
import streamlit as st

import auth

st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}</style>",
            unsafe_allow_html=True)
_, mid, _ = st.columns([1, 1.5, 1])
with mid:
    st.markdown('<div class="masthead"><h1>Driver Assurance</h1><span>Driver sign-in</span></div>',
                unsafe_allow_html=True)
    tab_in, tab_new = st.tabs(["Sign in", "Create driver account"])

    with tab_in:
        with st.form("signin"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", use_container_width=True):
                user, msg = auth.login(u, p)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                st.error(msg)

    with tab_new:
        st.markdown('<div class="auth-note">The emergency contact is notified by SMS if you stay over the speed '
                    'limit. Use the number with country code.</div>', unsafe_allow_html=True)
        with st.form("register"):
            a, b = st.columns(2)
            name = a.text_input("Full name")
            uname = b.text_input("Username")
            pw = a.text_input("Password", type="password")
            pw2 = b.text_input("Confirm password", type="password")
            en = a.text_input("Emergency contact name")
            ep = b.text_input("Emergency contact number", placeholder="+919810012345")
            plate = a.text_input("Vehicle registration")
            lic = b.text_input("Driving licence number")
            email = st.text_input("Email (optional)")
            if st.form_submit_button("Create account", use_container_width=True):
                if pw != pw2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = auth.register(name, uname, pw, en, ep, plate, lic, email)
                    if ok:
                        user, _ = auth.login(uname, pw)
                        st.session_state["user"] = user
                        st.rerun()
                    st.error(msg)
