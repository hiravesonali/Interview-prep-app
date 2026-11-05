"""Practice session page: setup → question loop → summary."""

from __future__ import annotations

import streamlit as st

from interview_app.features.practice import (
    PracticeSession,
    coach_stream,
    evaluate_answer,
    generate_question_set,
)
from interview_app.guard import GuardBlocked
from interview_app.llm.client import StructuredOutputError
from interview_app.models import Difficulty, QuestionSet, QuestionType
from interview_app.roles import find_role, load_roles
from interview_app.ui import state
from interview_app.ui.components import (
    render_feedback,
    render_question_card,
    section_header,
    show_guard_block,
    step_header,
)


def render() -> None:
    section_header("Practice <span>session</span>")
    session: PracticeSession | None = st.session_state.get("practice")
    if session is None:
        _setup()
    elif session.is_finished:
        _summary(session)
    else:
        _question_loop(session)


# ---------- setup ----------

_CUSTOM_ROLE = "Custom job title…"
_MINUTES_PER_QUESTION = 3
_MODE_LABELS = {"guided": "Guided", "mock": "Mock interview"}
_MODE_CAPTIONS = {
    "guided": "A coaching tip and hints before each answer. Best for learning.",
    "mock": "Like a real interview: questions only, scores at the end.",
}
_DIFFICULTY_LABELS = {"junior": "Junior", "mid": "Mid-level", "senior": "Senior"}
_DIFFICULTY_HELP = {
    "junior": 'definitions and basics, e.g. "What is a REST API?"',
    "mid": "how and why things work, comparisons",
    "senior": "small real-world problems, design decisions and trade-offs",
}
_TYPE_LABELS = {
    "technical": "Technical",
    "system_design": "System design",
    "behavioural": "Behavioural",
    "role_specific": "Role-specific",
}


def _role_picker(default: str) -> str:
    """Preset dropdown with a custom-title escape hatch. Returns the role name ('' if none)."""
    roles = load_roles()
    names = [r.name for r in roles]
    options = [*names, _CUSTOM_ROLE]
    if default in names:
        index: int | None = names.index(default)
    elif default:
        index = len(names)  # custom title coming from the dashboard or a JD analysis
    else:
        index = None
    choice = st.selectbox(
        "Role",
        options,
        index=index,
        placeholder="Choose a role…",
        format_func=lambda n: n if n == _CUSTOM_ROLE else f"{find_role(n).icon} {n}",
        key="setup_role",
    )
    if choice is None:
        return ""
    if choice == _CUSTOM_ROLE:
        return st.text_input(
            "Job title",
            value=default if default not in names else "",
            placeholder="e.g. Mobile Developer, Solutions Architect…",
            max_chars=120,
            key="setup_custom_role",
        ).strip()
    preset = find_role(choice)
    if preset:
        st.caption("Topics: " + ", ".join(preset.topics))
    return choice


def _setup() -> None:
    pending: QuestionSet | None = st.session_state.get("pending_question_set")
    role_default = pending.role if pending else state.current_role_name()

    if pending:
        st.info(
            f"**{len(pending.questions)} questions** loaded from the job-description analysis "
            f"for **{pending.role}**. Choose how to practise and start."
        )
    with st.container(key="setup"):
        step_header(1, "Who are you interviewing for?", "Pick a preset or type any job title.")
        role = _role_picker(role_default)

        step_header(2, "How do you want to practise?")
        c1, c2 = st.columns(2, gap="large")
        mode = c1.radio(
            "Mode",
            list(_MODE_LABELS),
            format_func=_MODE_LABELS.__getitem__,
            captions=list(_MODE_CAPTIONS.values()),
            key="setup_mode",
        )
        difficulty = (
            c2.segmented_control(
                "Difficulty",
                [d.value for d in Difficulty],
                format_func=_DIFFICULTY_LABELS.__getitem__,
                default=Difficulty.MID.value,
                key="setup_difficulty",
                disabled=pending is not None,
            )
            or Difficulty.MID.value
        )
        c2.caption(f"{_DIFFICULTY_LABELS[difficulty]}: {_DIFFICULTY_HELP[difficulty]}")

        if pending:
            step_header(3, "What to ask", "Already decided by the job description.")
            types = [t.value for t in QuestionType]
            count = len(pending.questions)
        else:
            step_header(3, "What to ask")
            types = st.pills(
                "Question types",
                [t.value for t in QuestionType],
                selection_mode="multi",
                default=[t.value for t in QuestionType][:3],
                format_func=_TYPE_LABELS.__getitem__,
                key="setup_types",
            )
            count = st.slider(
                "Number of questions",
                3,
                15,
                10,
                key="setup_count",
                help=f"Plan on about {_MINUTES_PER_QUESTION} minutes per question.",
            )

        minutes = count * _MINUTES_PER_QUESTION
        what = f"{count} {_DIFFICULTY_LABELS[difficulty].lower()} questions"
        if role:
            what += f" for {role}"
        summary = f"**{what}** · {_MODE_LABELS[mode].lower()} · about {minutes} minutes"
        st.markdown(summary)
        go = st.button(
            "Start practice",
            type="primary",
            key="setup_go",
            disabled=not role or not types,
        )
        if not role:
            st.caption("Choose a role to start.")
        elif not types:
            st.caption("Pick at least one question type.")
        elif not pending:
            st.caption("Generating the questions takes 10-30 seconds.")

    if pending and st.button("Discard JD questions, generate fresh ones instead"):
        st.session_state.pending_question_set = None
        st.rerun()

    if not go:
        return
    if pending:
        qs = pending
        qs.role = role
        source = "jd"
        st.session_state.pending_question_set = None
    else:
        qs = _generate(role, difficulty, types, count)
        source = "generated"
        if qs is None:
            return
    st.session_state.practice = PracticeSession(
        role=role,
        mode=mode,
        question_set=qs,
        feedback_technique=st.session_state.feedback_technique,
        source=source,
    )
    st.rerun()


def _generate(role: str, difficulty: str, types: list[str], count: int) -> QuestionSet | None:
    preset = find_role(role)
    topics = list(preset.topics) if preset else []
    try:
        with st.spinner(f"Generating {count} questions for {role}… (10-30 s)"):
            return generate_question_set(
                state.pipeline(),
                role,
                difficulty=Difficulty(difficulty),
                types=[QuestionType(t) for t in types] or list(QuestionType),
                topics=topics,
                count=count,
                model=state.current_model(),
            )
    except GuardBlocked as err:
        show_guard_block(err)
    except StructuredOutputError as err:
        st.error(f"Question generation failed, please retry. ({err})")
    return None


# ---------- question loop ----------


def _question_loop(session: PracticeSession) -> None:
    q = session.current
    st.progress(
        session.index / session.total,
        text=f"Question {session.index + 1} of {session.total} · {session.role} · "
        f"{session.mode} mode",
    )
    render_question_card(q, key="question_card")

    if session.mode == "guided":
        _guided_help(session)

    answered = q.id in session.answers
    with st.form(f"answer-{q.id}", clear_on_submit=False):
        answer = st.text_area(
            "Your answer (write it the way you would say it)",
            value=session.answers.get(q.id, ""),
            height=200,
            max_chars=6000,
            disabled=answered,
        )
        submitted = st.form_submit_button("Submit answer", type="primary", disabled=answered)

    if submitted:
        if not answer.strip():
            st.warning("Write an answer first.")
        else:
            session.answers[q.id] = answer
            if session.mode == "guided":
                _evaluate(session, q.id)
            # Save after every answer so an abandoned session can be resumed from the dashboard.
            state.store().save_session(session)
            st.rerun()

    if answered and session.mode == "guided" and q.id in session.feedback:
        render_feedback(session.feedback[q.id])

    c1, c2 = st.columns([1, 5])
    if (answered or session.mode == "mock") and c1.button(
        "Next question ➜" if not session.is_last else "Finish session 🏁", type="primary"
    ):
        session.advance()
        if session.is_finished and session.mode == "mock":
            _evaluate_all(session)
        if session.is_finished:
            state.store().save_session(session)
        st.rerun()
    if c2.button("Skip this question"):
        session.advance()
        if session.is_finished:
            if session.mode == "mock":
                _evaluate_all(session)
            state.store().save_session(session)
        st.rerun()


def _guided_help(session: PracticeSession) -> None:
    q = session.current
    with st.container(border=True):
        st.markdown("**🧭 Guided mode**")
        c1, c2 = st.columns(2)
        revealed = session.hints_revealed.get(q.id, 0)
        if c1.button(f"Reveal hint ({revealed}/{len(q.hints)})", disabled=revealed >= len(q.hints)):
            session.reveal_hint(q.id)
            st.rerun()
        for i in range(revealed):
            st.markdown(f"💡 **Hint {i + 1}:** {q.hints[i]}")

        if q.id in session.coaching:
            st.markdown(session.coaching[q.id])
            return
        note = st.text_input(
            "Tell the coach where you are stuck (optional)",
            placeholder="e.g. I know token bucket but not how to explain the trade-offs",
            max_chars=500,
            key=f"coach_note_{q.id}",
        )
        if c2.button("Coach me step by step"):
            slot = st.empty()
            text = ""
            try:
                for chunk in coach_stream(
                    state.pipeline(), session.role, q, note=note, model=state.current_model()
                ):
                    text += chunk
                    slot.markdown(text + "▌")
            except GuardBlocked as err:
                slot.empty()
                show_guard_block(err)
            else:
                slot.markdown(text)
                session.coaching[q.id] = text


def _evaluate(session: PracticeSession, qid: int) -> None:
    q = session.question_by_id(qid)
    try:
        with st.spinner("Evaluating your answer…"):
            session.feedback[qid] = evaluate_answer(
                state.pipeline(),
                session.role,
                q,
                session.answers[qid],
                technique=session.feedback_technique,
                model=state.current_model(),
            )
    except GuardBlocked as err:
        session.answers.pop(qid, None)
        show_guard_block(err)
        st.stop()
    except StructuredOutputError as err:
        session.answers.pop(qid, None)
        st.error(f"Feedback failed, please resubmit. ({err})")
        st.stop()


def _evaluate_all(session: PracticeSession) -> None:
    pending = [qid for qid in session.answers if qid not in session.feedback]
    bar = st.progress(0.0, text="Scoring your answers…")
    failed: list[str] = []
    for i, qid in enumerate(pending, 1):
        try:
            session.feedback[qid] = evaluate_answer(
                state.pipeline(),
                session.role,
                session.question_by_id(qid),
                session.answers[qid],
                technique=session.feedback_technique,
                model=state.current_model(),
            )
        except GuardBlocked as err:
            failed.append(
                f"Q{qid}: blocked by the {err.decision.layer} guard ({err.decision.reason})"
            )
        except StructuredOutputError as err:
            failed.append(f"Q{qid}: feedback failed ({err})")
        bar.progress(i / len(pending), text=f"Scored {i}/{len(pending)}")
    bar.empty()
    if failed:
        st.session_state.scoring_errors = failed


# ---------- summary ----------


def _summary(session: PracticeSession) -> None:
    st.subheader(f"🏁 Session summary · {session.role}")
    answered = len(session.answers)
    st.caption(
        f"{session.mode} mode · {answered}/{session.total} answered · "
        f"started {session.started_at:%d %b %H:%M}"
    )
    if errors := st.session_state.pop("scoring_errors", None):
        st.warning("Some answers could not be scored:\n" + "\n".join(f"- {e}" for e in errors))
    if not session.feedback:
        st.info("No answers were scored.")
    else:
        cols = st.columns(5)
        cols[0].metric("Overall", f"{session.overall_average:.1f} / 5")
        for col, (dim, avg) in zip(cols[1:], session.dimension_averages.items(), strict=True):
            col.metric(dim.capitalize(), f"{avg:.1f}")

        weak = session.weak_questions()
        if weak:
            st.markdown("**Revise next:** " + ", ".join(f"{q.topic}" for q in weak))

        for q in session.questions:
            fb = session.feedback.get(q.id)
            label = f"Q{q.id} · {q.topic} · " + (f"{fb.overall}/5" if fb else "not answered")
            with st.expander(label):
                st.markdown(f"**{q.question}**")
                if q.id in session.answers:
                    st.markdown("**Your answer**")
                    st.write(session.answers[q.id])
                if fb:
                    render_feedback(fb)

    c1, c2 = st.columns(2)
    retry = session.retry_set()
    if retry and c1.button(f"Retry the {len(retry.questions)} weak questions", type="primary"):
        st.session_state.pending_question_set = retry
        st.session_state.practice = None
        st.rerun()
    if c2.button("New session"):
        st.session_state.practice = None
        st.rerun()
