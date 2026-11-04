"""Driver profile: details used in alerts, emergency contact, password."""
import os

import streamlit as st

import auth
from notifier import Notifier

user = st.session_state["user"]
st.markdown('<div class="masthead"><h1>Driver profile</h1><span>Details used in alerts and reports</span></div>',
            unsafe_allow_html=True)
left, right = st.columns(2, gap="large")

with left:
    with st.form("profile"):
        name = st.text_input("Full name", user["full_name"])
        plate = st.text_input("Vehicle registration", user["vehicle_plate"])
        lic = st.text_input("Driving licence number", user["license_no"])
        email = st.text_input("Email", user["email"])
        en = st.text_input("Emergency contact name", user["emergency_name"])
        ep = st.text_input("Emergency contact number", user["emergency_phone"])
        if st.form_submit_button("Save changes"):
            ok, msg = auth.update_profile(user["id"], full_name=name, vehicle_plate=plate, license_no=lic,
                                          email=email, emergency_name=en, emergency_phone=ep)
            if ok:
                st.session_state["user"] = auth.get_user(user["id"])
            (st.success if ok else st.error)(msg)

with right:
    st.markdown("#### Emergency notification")
    st.caption(f"Alerts go to {user['emergency_name']} at {user['emergency_phone']}. "
               "Send a test to confirm it works before you drive.")
    if st.button("Send test message"):
        st.info(Notifier().send_now(
            user["emergency_phone"], f"Test from Driver Assurance: {user['full_name']} has set you as an emergency "
            "contact. You will be messaged if they stay over the speed limit.", os.path.join("logs", user["username"])))
    st.markdown("#### Change password")
    with st.form("password"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        if st.form_submit_button("Update password"):
            ok, msg = auth.change_password(user["id"], old, new)
            (st.success if ok else st.error)(msg)
