"""Streamlit entry point: `uv run streamlit run app.py`."""

from __future__ import annotations

import sys
from pathlib import Path

# `uv sync` installs this project, so the package imports normally. Streamlit Community Cloud
# reads uv.lock but does not document whether it installs the project itself, so fall back to
# the src/ directory rather than fail at import time.
if not any(Path(p).name == "src" for p in sys.path):
    sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st  # noqa: E402

from interview_app.config import get_settings  # noqa: E402
from interview_app.ui import auth, state  # noqa: E402
from interview_app.ui.components import (  # noqa: E402
    render_sidebar_controls,
    render_sidebar_dynamic,
)
from interview_app.ui.pages import home, jd_analyzer, practice, prompt_lab  # noqa: E402
from interview_app.ui.theme import CSS  # noqa: E402

st.set_page_config(
    page_title="Hoot · AI Interview Prep",
    page_icon="🦉",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.html(CSS)
auth.export_secrets_to_env()  # must run before get_settings() is first called
auth.require_login(get_settings())
state.init_state(auth.current_user_id())

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
