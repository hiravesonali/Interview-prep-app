"""Practice session page (state machine lands on day 2)."""

from __future__ import annotations

import streamlit as st

from interview_app.ui import state


def render() -> None:
    st.title("🗣️ Practice session")
    role = state.current_role_name()
    if role:
        st.info(f"Target role: **{role}**")
    else:
        st.warning("Pick a role on the dashboard first.")
    st.caption("Question generation, guided coaching and feedback arrive on day 2.")
