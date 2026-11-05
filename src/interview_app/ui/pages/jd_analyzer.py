"""Job-description analyzer page: input card → overview + tabs (skills, questions, plan, ask)."""

from __future__ import annotations

import html

import streamlit as st

from interview_app.features.jd_analyzer import analyze_job_description, to_question_set
from interview_app.guard import GuardBlocked
from interview_app.llm.client import StructuredOutputError
from interview_app.models import JobAnalysis, QuestionType
from interview_app.ui import state
from interview_app.ui.components import (
    render_question_card,
    section_header,
    show_guard_block,
    step_header,
)

_TYPE_LABELS = {
    QuestionType.TECHNICAL: "Technical",
    QuestionType.SYSTEM_DESIGN: "System design",
    QuestionType.BEHAVIOURAL: "Behavioural",
    QuestionType.ROLE_SPECIFIC: "Role-specific",
}
_TYPE_ICONS = {
    QuestionType.TECHNICAL: "🔧",
    QuestionType.SYSTEM_DESIGN: "🏗️",
    QuestionType.BEHAVIOURAL: "🤝",
    QuestionType.ROLE_SPECIFIC: "🎯",
}
_PLACEHOLDER = (
    "Paste the job description here: title, responsibilities, requirements and the stack. "
    "Company blurbs and benefits can stay in, they are ignored."
)


def render() -> None:
    section_header(
        "Analyse a <span>job description</span>",
        "Find out what the role really asks for, which questions that interview loop will ask, "
        "and how to prepare day by day.",
    )
    analysis: JobAnalysis | None = st.session_state.get("jd_analysis")
    if analysis is None:
        _input_card()
    else:
        _render_analysis(analysis)


# ---------- input ----------


def _input_card() -> None:
    with st.container(key="jd_input"):
        step_header(
            1,
            "Paste the job description",
            "Title, responsibilities and requirements are enough.",
        )
        jd_text = st.text_area(
            "Job description",
            value=st.session_state.get("jd_last_text", ""),
            height=240,
            max_chars=12000,
            placeholder=_PLACEHOLDER,
            label_visibility="collapsed",
            key="jd_text",
        )
        step_header(2, "Options")
        c1, c2 = st.columns([3, 2], gap="large")
        title = c1.text_input(
            "Target title (optional)",
            value=state.current_role_name(),
            placeholder="Leave empty to use the title from the JD",
            max_chars=120,
            key="jd_title",
        )
        c1.caption('Set it when the JD title is vague, e.g. "Engineer II".')
        plan_days = (
            c2.segmented_control(
                "Prep plan length",
                [7, 14],
                format_func=lambda d: f"{d} days",
                default=7,
                key="jd_days",
            )
            or 7
        )
        c2.caption("About an hour a day. The last day is a mock interview.")
        go = st.button("Analyse job description", type="primary", key="jd_go")
        st.caption("Takes 30 to 60 seconds.")

    if not go:
        return
    if not jd_text.strip():
        st.warning("Paste a job description first.")
        return
    st.session_state.jd_last_text = jd_text
    _run_analysis(jd_text, title, plan_days)


def _run_analysis(jd_text: str, title: str, plan_days: int) -> None:
    try:
        with st.spinner("Analysing the job description… (30-60 s)"):
            result = analyze_job_description(
                state.pipeline(),
                jd_text,
                target_title=title,
                plan_days=plan_days,
                model=state.current_model(),
            )
    except GuardBlocked as err:
        show_guard_block(err)
        return
    except StructuredOutputError as err:
        st.error(f"The model did not return a valid analysis. Try again. ({err})")
        return
    st.session_state.jd_analysis = result.data
    st.toast(f"Done · {result.usage.total_tokens:,} tokens · ${result.usage.cost_usd:.4f}")
    st.rerun()


# ---------- results ----------


def _render_analysis(a: JobAnalysis) -> None:
    must_have = sum(len(g.must_have) for g in a.skill_groups)
    with st.container(key="jd_result"):
        st.html(
            '<div class="hoot-kicker">Role snapshot</div>'
            f"<h3>{html.escape(a.title)}</h3>"
            '<div class="hoot-badges">'
            f'<span class="hoot-badge">{html.escape(a.seniority)}</span>'
            f'<span class="hoot-badge alt">{html.escape(a.domain)}</span></div>'
            f"<p>{html.escape(a.summary)}</p>"
        )
        stats = [
            (must_have, "must-have skills"),
            (len(a.likely_questions), "likely questions"),
            (len(a.prep_plan), "day prep plan"),
            (len(a.red_flags), "red flags"),
        ]
        for col, (n, label) in zip(st.columns(4), stats, strict=True):
            col.html(f'<div class="hoot-stat"><b>{n}</b><span>{label}</span></div>')
        b1, b2, b3 = st.columns([1.3, 1.2, 1])
        if b1.button(
            f"🗣️ Practise these {len(a.likely_questions)} questions",
            type="primary",
            key="jd_practise",
            width="stretch",
        ):
            st.session_state.pending_question_set = to_question_set(a)
            st.session_state.practice = None
            st.switch_page(st.session_state.pages["practice"])
        if b2.button("📝 Tailor my resume for this JD", key="jd_tailor", width="stretch"):
            st.session_state.rb_prefill = {
                "jd_text": st.session_state.get("jd_last_text", ""),
                "job_title": a.title,
            }
            st.session_state.rb_tab = "tailored"
            st.session_state.rb_screen = ("new", None)
            st.switch_page(st.session_state.pages["resume"])
        if b3.button("Analyse another JD", key="jd_reset", width="stretch"):
            st.session_state.jd_analysis = None
            st.rerun()

    flags = f" ({len(a.red_flags)})" if a.red_flags else ""
    tab_skills, tab_q, tab_plan, tab_ask = st.tabs(
        [
            f"Skills ({must_have} must-have)",
            f"Likely questions ({len(a.likely_questions)})",
            f"Prep plan ({len(a.prep_plan)} days)",
            f"Ask & flags{flags}",
        ]
    )
    with tab_skills:
        _skills(a)
    with tab_q:
        _questions(a)
    with tab_plan:
        _plan(a)
    with tab_ask:
        _ask_and_flags(a)


def _chips(items: list[str], kind: str) -> str:
    return "".join(f'<span class="hoot-chip {kind}">{html.escape(s)}</span>' for s in items)


def _skills(a: JobAnalysis) -> None:
    st.html(
        '<div class="hoot-legend"><span class="hoot-chip must">must have</span>'
        '<span class="hoot-chip nice">nice to have</span></div>'
    )
    cols = st.columns(2, gap="medium")
    for i, group in enumerate(a.skill_groups):
        with cols[i % 2], st.container(key=f"jd_skill_{i}"):
            st.html(
                f'<div class="hoot-card-title">{html.escape(group.name)}</div>'
                f'<div class="hoot-chips">{_chips(group.must_have, "must")}'
                f"{_chips(group.nice_to_have, 'nice')}</div>"
            )


def _questions(a: JobAnalysis) -> None:
    st.caption("Open a card for what a strong answer covers and the hints.")
    for qtype in QuestionType:
        qs = [q for q in a.likely_questions if q.type == qtype]
        if not qs:
            continue
        st.html(
            f'<div class="hoot-group">{_TYPE_ICONS[qtype]} {_TYPE_LABELS[qtype]} '
            f"<small>{len(qs)}</small></div>"
        )
        for q in qs:
            render_question_card(q, show_details=True, key=f"jd_q_{q.id}")


def _plan(a: JobAnalysis) -> None:
    st.caption("Tick tasks as you go. The plan lives in this browser tab only.")
    for day in a.prep_plan:
        with st.container(key=f"jd_day_{day.day}"):
            st.html(
                f'<div class="hoot-day"><span class="hoot-day-no">Day {day.day}</span>'
                f"<b>{html.escape(day.focus)}</b></div>"
            )
            for task in day.tasks:
                st.checkbox(task, key=f"plan-{a.title}-{day.day}-{task[:30]}")


def _ask_and_flags(a: JobAnalysis) -> None:
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(key="jd_ask"):
        st.html(
            '<div class="hoot-card-title">💬 Questions to ask the interviewer</div><ul>'
            + "".join(f"<li>{html.escape(q)}</li>" for q in a.questions_to_ask)
            + "</ul>"
        )
    with c2, st.container(key="jd_flags"):
        items = (
            "".join(f"<li>⚠️ {html.escape(r)}</li>" for r in a.red_flags)
            or '<li class="hoot-muted">None spotted in this JD.</li>'
        )
        st.html(f'<div class="hoot-card-title">🚩 Red flags</div><ul>{items}</ul>')
