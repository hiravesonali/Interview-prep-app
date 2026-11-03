"""Prompt Lab: compare 5 system-prompt techniques on the same answer (lands on day 4)."""

from __future__ import annotations

import streamlit as st

from interview_app.ui.components import section_header


def render() -> None:
    section_header("Prompt <span>Lab</span>")
    st.caption(
        "Runs one question + answer through five feedback prompts (zero-shot, few-shot, "
        "chain-of-thought, role + rubric, self-critique) and compares cost, latency and quality."
    )
