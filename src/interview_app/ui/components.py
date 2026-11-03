"""Reusable UI pieces: sidebar controls, cost meter, security log, guard error banner."""

from __future__ import annotations

import streamlit as st

from interview_app.config import AVAILABLE_MODELS
from interview_app.guard import GuardBlocked
from interview_app.ui import state


def render_sidebar_controls() -> None:
    """Static controls. Call before the page runs so pages see the chosen values."""
    s = state.settings()
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        if not s.has_api_key:
            st.error("No OPENROUTER_API_KEY found. Copy `.env.example` to `.env` and add your key.")

        models = list(AVAILABLE_MODELS)
        if s.default_model not in models:
            models.insert(0, s.default_model)
        st.session_state.model = st.selectbox(
            "Model", models, index=models.index(st.session_state.model), key="model_select"
        )

        pipe = state.pipeline()
        pipe.llm_guard_enabled = st.toggle(
            "LLM guard (classifier)",
            value=pipe.llm_guard_enabled,
            help=f"Runs every input through {s.guard_model} after the rule-based guard.",
        )

        # Dynamic panels are filled after the page ran (see app.py), so the log and
        # cost meter reflect this run's guard decisions and calls, not the previous run's.
        st.session_state.sidebar_dynamic = st.container()


def render_sidebar_dynamic() -> None:
    with st.session_state.sidebar_dynamic:
        render_cost_meter()
        render_security_log()


def render_cost_meter() -> None:
    t = state.tracker()
    limit = state.settings().max_session_cost_usd
    st.markdown("### 💸 Session usage")
    c1, c2 = st.columns(2)
    c1.metric("Cost (USD)", f"{t.total_cost_usd:.4f}")
    c2.metric("Tokens", f"{t.total_tokens:,}")
    st.caption(f"{len(t.calls)} calls · soft limit ${limit:.2f}")
    if t.total_cost_usd > limit:
        st.warning("Session cost is above the soft limit.")


def render_security_log() -> None:
    log = state.security_log()
    counts = log.counts
    title = (
        f"🛡️ Security log · {counts.get('block', 0)} blocked · "
        f"{counts.get('redact', 0)} redacted · {counts.get('allow', 0)} allowed"
    )
    with st.expander(title, expanded=False):
        if not log.entries:
            st.caption("No guard decisions yet.")
        for e in reversed(log.entries[-30:]):
            icon = {"allow": "✅", "redact": "✂️", "block": "⛔"}[e.action]
            detail = f" `{', '.join(e.matches)}`" if e.matches else ""
            st.markdown(
                f"{icon} **{e.layer}** · {e.kind} · {e.category}{detail}  \n"
                f"<small>{e.time:%H:%M:%S} — {e.reason}</small>",
                unsafe_allow_html=True,
            )


def show_guard_block(err: GuardBlocked) -> None:
    d = err.decision
    st.error(f"🛡️ Request blocked by the {d.layer} guard ({d.category}): {d.reason}")
