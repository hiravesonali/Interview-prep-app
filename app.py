"""Streamlit entry point: `uv run streamlit run app.py`."""

from __future__ import annotations

import streamlit as st

from interview_app.ui import state
from interview_app.ui.components import render_sidebar_controls, render_sidebar_dynamic
from interview_app.ui.pages import home, jd_analyzer, practice, prompt_lab

st.set_page_config(page_title="Interview Practice", page_icon="🎯", layout="wide")

state.init_state()

pages = {
    "home": st.Page(home.render, title="Dashboard", icon="🏠", default=True, url_path="home"),
    "practice": st.Page(practice.render, title="Practice session", icon="🗣️", url_path="practice"),
    "jd": st.Page(jd_analyzer.render, title="JD analyzer", icon="📄", url_path="jd"),
    "lab": st.Page(prompt_lab.render, title="Prompt Lab", icon="🧪", url_path="lab"),
}
st.session_state.pages = pages

nav = st.navigation(list(pages.values()))
render_sidebar_controls()
nav.run()
render_sidebar_dynamic()
