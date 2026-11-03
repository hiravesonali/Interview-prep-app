"""Reusable UI pieces: branded sidebar, cost card, security log, question/feedback cards."""

from __future__ import annotations

import html

import streamlit as st

from interview_app.config import AVAILABLE_MODELS
from interview_app.guard import GuardBlocked
from interview_app.llm.prompts import list_prompts
from interview_app.models import AnswerFeedback, Question
from interview_app.ui import state
from interview_app.ui.theme import APP_NAME, APP_TAGLINE, mascot

_TECHNIQUE_LABELS = {
    "01_zero_shot": "Zero-shot",
    "02_few_shot": "Few-shot",
    "03_chain_of_thought": "Chain-of-thought",
    "04_role_rubric": "Role + rubric",
    "05_self_critique": "Self-critique",
}

# key -> (label, icon). Order = sidebar order. Keys match app.py's pages dict.
# The Prompt Lab is a developer tool (course evidence), so it is linked from the
# Developer settings expander instead of the user-facing menu.
NAV: dict[str, tuple[str, str]] = {
    "home": ("Dashboard", "🏠"),
    "practice": ("Practice session", "🗣️"),
    "jd": ("JD analyzer", "📄"),
}
DEV_NAV: dict[str, tuple[str, str]] = {"lab": ("Prompt Lab", "🧪")}


def technique_label(name: str) -> str:
    stem = name.rsplit("/", 1)[-1]
    return _TECHNIQUE_LABELS.get(stem, stem)


# ---------- sidebar ----------


def render_sidebar_controls(active: str) -> None:
    """Brand, welcome, menu and settings. Runs before the page so pages see the values."""
    s = state.settings()
    first_name = (s.user_name.split() or ["there"])[0]
    with st.sidebar:
        with st.container(key="brand"):  # sticky; see theme.py
            st.html(
                f'<div class="hoot-brand">{mascot(52)}<div><div class="name">{APP_NAME}</div>'
                f'<div class="tag">{APP_TAGLINE}</div></div></div>'
            )
        st.html(
            f'<div class="hoot-welcome">Welcome <b>{html.escape(first_name)}</b> 👋<br>'
            f"<span class='sub'>Let's practise 🚀</span></div>"
        )
        if not s.has_api_key:
            st.error("No OPENROUTER_API_KEY found. Copy `.env.example` to `.env` and add your key.")

        st.html('<div class="hoot-menu-label">MAIN MENU</div>')
        _nav_links(NAV, active)

        with st.expander("⚙️ Developer settings", expanded=active in DEV_NAV):
            st.caption("Model, sampling and guard knobs. Regular users never need these.")
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
            techniques = list_prompts("feedback")
            current = st.session_state.get("feedback_technique", techniques[0])
            st.session_state.feedback_technique = st.selectbox(
                "Feedback prompt technique",
                techniques,
                index=techniques.index(current) if current in techniques else 0,
                format_func=technique_label,
                help="Which system-prompt variant scores your answers (see Prompt Lab).",
            )
            _render_sampling_controls(pipe)
            st.html('<div class="hoot-menu-label">TOOLS</div>')
            _nav_links(DEV_NAV, active)
            st.caption("Compare the five feedback prompts and pick the default grader above.")

        # Filled after the page ran (see app.py) so cost and log reflect this run.
        st.session_state.sidebar_dynamic = st.container()

        if s.user_name or s.user_email:
            initial = (s.user_name or s.user_email)[:1].upper()
            st.html(
                f'<div class="hoot-user"><div class="hoot-avatar">{initial}</div><div>'
                f'<div class="n">{html.escape(s.user_name)}</div>'
                f'<div class="e">{html.escape(s.user_email)}</div></div></div>'
            )


def _nav_links(items: dict[str, tuple[str, str]], active: str) -> None:
    for key, (label, icon) in items.items():
        if key == active:
            st.html(f'<div class="hoot-nav-active"><span>{icon}</span>{label}</div>')
        else:
            st.page_link(st.session_state.pages[key], label=label, icon=icon)


def _render_sampling_controls(pipe) -> None:
    """Temperature / max-tokens sliders. Off = each task keeps its own tuned defaults."""
    custom = st.toggle(
        "Override temperature & max tokens",
        value=pipe.overrides.temperature is not None,
        help=(
            "Default: question generation 0.6, feedback/JD analysis 0.2, coaching 0.5; "
            "max tokens sized per task. Turn on to experiment."
        ),
    )
    if not custom:
        pipe.overrides.temperature = None
        pipe.overrides.max_tokens = None
        return
    pipe.overrides.temperature = st.slider(
        "Temperature",
        0.0,
        1.5,
        value=pipe.overrides.temperature if pipe.overrides.temperature is not None else 0.4,
        step=0.1,
        help="Applies to every call to the main model. Lower = more deterministic scoring.",
    )
    pipe.overrides.max_tokens = st.slider(
        "Max tokens (coaching text)",
        200,
        4000,
        value=pipe.overrides.max_tokens or 2000,
        step=100,
        help="Caps the streamed coaching reply. Structured JSON calls keep their own budget.",
    )


def render_sidebar_dynamic() -> None:
    with st.session_state.sidebar_dynamic:
        render_cost_card()
        render_security_log()


def render_cost_card() -> None:
    t = state.tracker()
    limit = state.settings().max_session_cost_usd
    over = t.total_cost_usd > limit
    st.html(
        '<div class="hoot-usage"><div class="row"><div><div class="label">Session cost</div>'
        f'<div class="big">${t.total_cost_usd:.3f}</div></div><div><div class="label">Tokens</div>'
        f'<div class="big">{t.total_tokens:,}</div></div></div>'
        f'<div class="small">{len(t.calls)} calls · soft limit ${limit:.2f}'
        f"{' · ⚠️ over limit' if over else ''}</div></div>"
    )


def render_security_log() -> None:
    log = state.security_log()
    counts = log.counts
    if failed := log.fail_open_entries:
        st.warning(
            f"LLM guard unavailable ({len(failed)}×): {failed[-1].reason.split(': ', 1)[-1]}. "
            "Inputs were allowed by the rule-based guard only."
        )
    title = f"🛡️ Security log · {counts.get('block', 0)} blocked"
    with st.expander(title, expanded=False):
        if not log.entries:
            st.caption("No guard decisions yet.")
        for e in reversed(log.entries[-30:]):
            icon = {"allow": "✅", "redact": "✂️", "block": "⛔"}[e.action]
            detail = f" · <code>{html.escape(', '.join(e.matches))}</code>" if e.matches else ""
            st.html(
                f'<div class="hoot-log">{icon} <b>{e.layer}</b> · {e.kind} · {e.category}{detail}'
                f"<br><small>{e.time:%H:%M:%S} — {html.escape(e.reason)}</small></div>"
            )


def show_guard_block(err: GuardBlocked) -> None:
    d = err.decision
    st.error(f"🛡️ Request blocked by the {d.layer} guard ({d.category}): {d.reason}")


# ---------- content cards ----------

_TYPE_ICON = {
    "technical": "🔧",
    "system_design": "🏗️",
    "behavioural": "🤝",
    "role_specific": "🎯",
}


def section_header(title_html: str, subtitle: str = "") -> None:
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.html(f'<div class="hoot-section"><h2>{title_html}</h2>{sub}</div>')


def render_question_card(
    q: Question, *, show_details: bool = False, key: str | None = None
) -> None:
    container = st.container(key=key) if key else st.container(border=True)
    with container:
        st.html(
            f'<div class="hoot-kicker">{_TYPE_ICON.get(q.type.value, "")} '
            f"{q.type.value.replace('_', ' ')} · {html.escape(q.topic)}</div>"
            f"<h3>{html.escape(q.question)}</h3>"
        )
        if show_details:
            with st.expander("What a strong answer covers · hints"):
                st.markdown("\n".join(f"- {p}" for p in q.strong_answer_covers))
                for i, h in enumerate(q.hints, 1):
                    st.markdown(f"💡 **Hint {i}:** {h}")


def render_feedback(fb: AnswerFeedback) -> None:
    with st.container(border=True):
        cols = st.columns(5)
        cols[0].metric("Overall", f"{fb.overall} / 5")
        for col, s in zip(cols[1:], fb.scores, strict=False):
            col.metric(s.dimension.capitalize(), s.score, help=s.comment)
        c1, c2 = st.columns(2)
        c1.markdown("**✅ Strengths**\n" + "\n".join(f"- {x}" for x in fb.strengths))
        c2.markdown("**🔍 Gaps**\n" + "\n".join(f"- {x}" for x in fb.gaps))
        if fb.analysis:
            with st.expander("Model's reasoning"):
                st.write(fb.analysis)
        with st.expander("Model answer"):
            st.write(fb.model_answer)
        st.markdown(f"**Likely follow-up:** {fb.follow_up_question}")
