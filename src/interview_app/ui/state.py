"""Streamlit session-state bootstrap: one client, tracker, log and pipeline per browser session."""

from __future__ import annotations

import streamlit as st

from interview_app.config import Settings, get_settings
from interview_app.guard import GuardPipeline, SecurityLog
from interview_app.llm.client import OpenRouterClient, UsageTracker
from interview_app.storage.store import Store, open_store


def init_state() -> None:
    if "settings" in st.session_state:
        return
    settings: Settings = get_settings()
    tracker = UsageTracker()
    log = SecurityLog()
    client = OpenRouterClient(settings, tracker)
    st.session_state.settings = settings
    st.session_state.tracker = tracker
    st.session_state.security_log = log
    st.session_state.client = client
    st.session_state.pipeline = GuardPipeline(client, settings, log)
    st.session_state.store = open_store(settings)
    st.session_state.model = settings.default_model
    st.session_state.selected_role = None
    st.session_state.custom_title = ""
    # Default grader = the Prompt Lab winner (README → Results).
    st.session_state.feedback_technique = "feedback/04_role_rubric"
    st.session_state.practice = None
    st.session_state.pending_question_set = None
    st.session_state.jd_analysis = None


def pipeline() -> GuardPipeline:
    return st.session_state.pipeline


def settings() -> Settings:
    return st.session_state.settings


def store() -> Store:
    return st.session_state.store


def tracker() -> UsageTracker:
    return st.session_state.tracker


def security_log() -> SecurityLog:
    return st.session_state.security_log


def current_model() -> str:
    return st.session_state.model


def current_role_name() -> str:
    """Selected preset role name or the custom title; empty string if neither."""
    return st.session_state.selected_role or st.session_state.custom_title or ""
