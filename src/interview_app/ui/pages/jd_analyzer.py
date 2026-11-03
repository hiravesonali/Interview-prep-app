"""Job-description analyzer page (lands on day 2)."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.title("📄 Job description analyzer")
    st.caption("Paste a JD → skills, likely questions, prep plan. Arrives on day 2.")
