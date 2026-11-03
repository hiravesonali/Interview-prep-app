"""Job-description analyzer page."""

from __future__ import annotations

import streamlit as st

from interview_app.features.jd_analyzer import analyze_job_description, to_question_set
from interview_app.guard import GuardBlocked
from interview_app.llm.client import StructuredOutputError
from interview_app.models import JobAnalysis, QuestionType
from interview_app.ui import state
from interview_app.ui.components import render_question_card, show_guard_block

_TYPE_LABELS = {
    QuestionType.TECHNICAL: "Technical",
    QuestionType.SYSTEM_DESIGN: "System design",
    QuestionType.BEHAVIOURAL: "Behavioural",
    QuestionType.ROLE_SPECIFIC: "Role-specific",
}


def render() -> None:
    st.title("📄 Job description analyzer")
    st.caption("Paste a JD → required skills, likely interview questions, day-by-day prep plan.")

    with st.form("jd_form"):
        jd_text = st.text_area(
            "Job description",
            height=260,
            max_chars=12000,
            placeholder="Paste the full job description here…",
        )
        c1, c2 = st.columns([2, 1])
        title = c1.text_input(
            "Target title (optional)",
            value=state.current_role_name(),
            max_chars=120,
        )
        plan_days = c2.radio(
            "Prep plan length", [7, 14], horizontal=True, format_func=lambda d: f"{d} days"
        )
        submitted = st.form_submit_button("Analyse", type="primary")

    if submitted:
        if not jd_text.strip():
            st.warning("Paste a job description first.")
        else:
            _run_analysis(jd_text, title, plan_days)

    analysis: JobAnalysis | None = st.session_state.get("jd_analysis")
    if analysis:
        _render_analysis(analysis)


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


def _render_analysis(a: JobAnalysis) -> None:
    st.divider()
    st.subheader(a.title)
    st.markdown(f"**Seniority:** {a.seniority} · **Domain:** {a.domain}")
    st.write(a.summary)

    if st.button("🗣️ Practice these questions", type="primary"):
        st.session_state.pending_question_set = to_question_set(a)
        st.session_state.practice = None
        st.switch_page(st.session_state.pages["practice"])

    tab_skills, tab_q, tab_plan, tab_ask = st.tabs(
        ["Skills", f"Likely questions ({len(a.likely_questions)})", "Prep plan", "Ask & flags"]
    )
    with tab_skills:
        for group in a.skill_groups:
            with st.container(border=True):
                st.markdown(f"**{group.name}**")
                c1, c2 = st.columns(2)
                c1.markdown("Must have")
                c1.markdown("\n".join(f"- {s}" for s in group.must_have) or "_none_")
                c2.markdown("Nice to have")
                c2.markdown("\n".join(f"- {s}" for s in group.nice_to_have) or "_none_")
    with tab_q:
        for qtype in QuestionType:
            qs = [q for q in a.likely_questions if q.type == qtype]
            if not qs:
                continue
            st.markdown(f"#### {_TYPE_LABELS[qtype]}")
            for q in qs:
                render_question_card(q, show_details=True)
    with tab_plan:
        for day in a.prep_plan:
            with st.container(border=True):
                st.markdown(f"**Day {day.day} · {day.focus}**")
                for task in day.tasks:
                    st.checkbox(task, key=f"plan-{a.title}-{day.day}-{task[:30]}")
    with tab_ask:
        st.markdown("**Questions to ask the interviewer**")
        st.markdown("\n".join(f"- {q}" for q in a.questions_to_ask))
        st.markdown("**Red flags**")
        st.markdown("\n".join(f"- ⚠️ {r}" for r in a.red_flags) or "_none spotted_")
