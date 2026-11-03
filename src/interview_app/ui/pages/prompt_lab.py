"""Prompt Lab: compare the feedback prompt techniques on one question + answer."""

from __future__ import annotations

import streamlit as st

from interview_app.config import AVAILABLE_MODELS
from interview_app.features.prompt_lab import (
    SAMPLE_ANSWERS,
    SAMPLE_QUESTION,
    LabResult,
    judge_results,
    run_comparison,
)
from interview_app.llm.prompts import list_prompts
from interview_app.models import Question, QuestionType
from interview_app.storage.history import list_sessions, load_session
from interview_app.storage.prompt_lab import (
    LabRecord,
    append_records,
    leaderboard,
    load_records,
    now_iso,
)
from interview_app.ui import state
from interview_app.ui.components import render_feedback, section_header, technique_label


def render() -> None:
    section_header(
        "Prompt <span>Lab</span>",
        "One question and answer, several system-prompt techniques. Compare quality, cost and "
        "latency, rate each result, and the leaderboard builds up over time.",
    )
    question, answer, role = _pick_input()
    techniques = _pick_techniques()
    judge_model = _pick_judge()

    if st.button("Run comparison", type="primary", disabled=not (question and answer.strip())):
        _run(role, question, answer, techniques, judge_model)

    results: list[LabResult] | None = st.session_state.get("lab_results")
    if results:
        _show_results(results, question, answer)
    _leaderboard()


# ---------- input ----------


def _pick_input() -> tuple[Question | None, str, str]:
    with st.container(key="lab_input"):
        source = st.radio(
            "Source", ["Sample", "From a saved session", "Write my own"], horizontal=True
        )
        role = st.text_input("Role", value=state.current_role_name() or "AI Engineer")
        if source == "Sample":
            level = st.radio("Sample answer", list(SAMPLE_ANSWERS), horizontal=True, index=1)
            st.markdown(f"**{SAMPLE_QUESTION.question}**")
            st.caption(SAMPLE_ANSWERS[level])
            return SAMPLE_QUESTION, SAMPLE_ANSWERS[level], role
        if source == "From a saved session":
            sessions = list_sessions(state.settings().data_dir, limit=20)
            answered = []
            for s in sessions:
                sess = load_session(s.path)
                answered += [
                    (f"{sess.role} · {sess.started_at:%d %b %H:%M} · Q{q.id} {q.topic}", q, a)
                    for q in sess.questions
                    if (a := sess.answers.get(q.id))
                ]
            if not answered:
                st.info("No answered questions in history yet. Finish a practice session first.")
                return None, "", role
            label = st.selectbox("Answered question", [x[0] for x in answered])
            _, q, a = next(x for x in answered if x[0] == label)
            st.markdown(f"**{q.question}**")
            st.caption(a)
            return q, a, role
        q_text = st.text_area("Question", height=80)
        c1, c2 = st.columns(2)
        q_type = c1.selectbox("Type", [t.value for t in QuestionType])
        topic = c2.text_input("Topic", value="general")
        answer = st.text_area("Answer", height=160)
        if not q_text.strip():
            return None, answer, role
        q = Question(
            id=1,
            type=QuestionType(q_type),
            topic=topic or "general",
            question=q_text.strip(),
            strong_answer_covers=[],
            hints=["-"],
        )
        return q, answer, role


def _pick_techniques() -> list[str]:
    all_techniques = list_prompts("feedback")
    return st.multiselect(
        "Techniques to run",
        all_techniques,
        default=all_techniques,
        format_func=technique_label,
    )


def _pick_judge() -> str | None:
    """LLM-as-a-judge: rates each feedback on accuracy, specificity, actionability and
    calibration. Default judge is a different model family than the one writing the
    feedback, to reduce self-preference bias."""
    c1, c2 = st.columns([1, 2])
    enabled = c1.toggle("LLM judge", value=True, help="Adds one judge call per variant.")
    models = list(AVAILABLE_MODELS)
    preferred = next((m for m in models if m != state.current_model()), models[0])
    judge_model = c2.selectbox(
        "Judge model", models, index=models.index(preferred), disabled=not enabled
    )
    return judge_model if enabled else None


# ---------- run + results ----------


def _run(
    role: str, question: Question, answer: str, techniques: list[str], judge_model: str | None
) -> None:
    if not techniques:
        st.warning("Pick at least one technique.")
        return
    with st.spinner(f"Running {len(techniques)} variants in parallel… (10-30 s)"):
        results = run_comparison(
            state.pipeline(), role, question, answer, techniques, model=state.current_model()
        )
    if judge_model:
        with st.spinner(f"Judging the results with {judge_model}…"):
            results = judge_results(
                state.pipeline(), role, question, answer, results, model=judge_model
            )
    st.session_state.lab_results = results
    st.session_state.lab_ratings = {}


def _show_results(results: list[LabResult], question: Question | None, answer: str) -> None:
    st.html('<div class="hoot-h2">Results</div>')
    cols = st.columns(len(results), gap="small")
    for col, r in zip(cols, results, strict=True):
        with col, st.container(key=f"lab_card_{r.technique.rsplit('/', 1)[-1]}"):
            st.markdown(f"**{technique_label(r.technique)}**")
            if not r.ok or r.feedback is None or r.usage is None:
                st.error(r.error or "failed")
                continue
            fb, u = r.feedback, r.usage
            st.metric("Overall", f"{fb.overall} / 5")
            st.caption(" · ".join(f"{s.dimension[:4]} {s.score}" for s in fb.scores))
            st.caption(f"${u.cost_usd:.4f} · {u.total_tokens:,} tok · {u.latency_s:.1f}s")
            st.caption(f"{len(fb.strengths)} strengths · {len(fb.gaps)} gaps")
            if r.judge:
                j = r.judge
                st.metric(
                    "Judge", f"{j.overall} / 5", help="LLM-as-a-judge rating of this feedback"
                )
                st.caption(
                    f"acc {j.accuracy} · spec {j.specificity} · act {j.actionability} · "
                    f"cal {j.calibration}"
                )
                with st.expander("Judge rationale"):
                    st.write(j.rationale)
            elif r.judge_error:
                st.caption(f"Judge failed: {r.judge_error}")
            with st.expander("Full feedback"):
                render_feedback(fb)
            stars = st.feedback("stars", key=f"rate_{r.technique}")
            st.session_state.lab_ratings[r.technique] = (stars + 1) if stars is not None else None

    note = st.text_input("Note for this run (optional)", key="lab_note")
    if st.button("Save results and ratings") and question is not None:
        records = [
            LabRecord(
                time=now_iso(),
                technique=r.technique,
                model=r.usage.model,
                question=question.question[:120],
                answer_preview=answer[:120],
                overall=r.feedback.overall,
                cost_usd=r.usage.cost_usd,
                latency_s=round(r.usage.latency_s, 2),
                tokens=r.usage.total_tokens,
                rating=st.session_state.lab_ratings.get(r.technique),
                note=note,
                judge_overall=r.judge.overall if r.judge else None,
                judge_model=r.judge_usage.model if r.judge_usage else "",
            )
            for r in results
            if r.ok and r.feedback is not None and r.usage is not None
        ]
        append_records(records, state.settings().data_dir)
        st.toast(f"Saved {len(records)} records.")
        st.rerun()


def _leaderboard() -> None:
    records = load_records(state.settings().data_dir)
    st.html('<div class="hoot-h2">Leaderboard</div>')
    if not records:
        st.caption("Run a comparison and save it to start the leaderboard.")
        return
    rows = leaderboard(records)
    st.dataframe(
        [
            {
                "Technique": technique_label(r.technique),
                "Runs": r.runs,
                "Your rating (avg)": r.avg_rating,
                "LLM judge (avg)": r.avg_judge,
                "Score given to answer (avg)": r.avg_overall,
                "Cost / run ($)": r.avg_cost_usd,
                "Latency (s)": r.avg_latency_s,
                "Tokens": r.avg_tokens,
            }
            for r in rows
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(f"{len(records)} saved runs · stored in data/prompt_lab.json")
