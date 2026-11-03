"""Streamlit entry point: `uv run streamlit run app.py`."""

from __future__ import annotations

import streamlit as st

from interview_app.ui import state
from interview_app.ui.components import render_sidebar_controls, render_sidebar_dynamic
from interview_app.ui.pages import home, jd_analyzer, practice, prompt_lab
from interview_app.ui.theme import CSS

st.set_page_config(
    page_title="Hoot · AI Interview Prep",
    page_icon="🦉",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.html(CSS)
state.init_state()

pages = {
    "home": st.Page(home.render, title="Dashboard", icon="🏠", default=True),
    "practice": st.Page(practice.render, title="Practice session", icon="🗣️", url_path="practice"),
    "jd": st.Page(jd_analyzer.render, title="JD analyzer", icon="📄", url_path="jd"),
    "lab": st.Page(prompt_lab.render, title="Prompt Lab", icon="🧪", url_path="lab"),
}
st.session_state.pages = pages

# position="hidden": we draw our own menu in the sidebar (see components.render_sidebar_controls)
nav = st.navigation(list(pages.values()), position="hidden")
active = next((k for k, p in pages.items() if p.title == nav.title), "home")

render_sidebar_controls(active)
nav.run()
render_sidebar_dynamic()
