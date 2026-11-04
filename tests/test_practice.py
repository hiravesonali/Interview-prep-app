from __future__ import annotations

from interview_app.features.jd_analyzer import to_question_set
from interview_app.features.practice import PracticeSession
from interview_app.models import (
    AnswerFeedback,
    Difficulty,
    DimensionScore,
    JobAnalysis,
    Question,
    QuestionSet,
    QuestionType,
)
from interview_app.storage.db import make_engine
from interview_app.storage.store import Store


def _q(i: int, topic: str = "t") -> Question:
    return Question(
        id=i,
        type=QuestionType.TECHNICAL,
        topic=f"{topic}{i}",
        question=f"Q{i}?",
        strong_answer_covers=["a"],
        hints=["h1", "h2", "h3"],
    )


def _fb(overall: int) -> AnswerFeedback:
    return AnswerFeedback(
        scores=[
            DimensionScore(dimension=d, score=overall, comment="c")
            for d in ("correctness", "depth", "structure", "communication")
        ],
        overall=overall,
        strengths=["s"],
        gaps=["g"],
        model_answer="m",
        follow_up_question="f",
    )


def _session(n: int = 3) -> PracticeSession:
    qs = QuestionSet(
        role="AI Engineer", difficulty=Difficulty.MID, questions=[_q(i) for i in range(1, n + 1)]
    )
    return PracticeSession(
        role="AI Engineer",
        mode="guided",
        question_set=qs,
        feedback_technique="feedback/01_zero_shot",
    )


def test_navigation_and_finish() -> None:
    s = _session(3)
    assert s.current.id == 1 and not s.is_last
    s.advance()
    s.advance()
    assert s.is_last and not s.is_finished
    s.advance()
    assert s.is_finished


def test_hints_cap_at_available() -> None:
    s = _session(1)
    for _ in range(5):
        s.reveal_hint(1)
    assert s.hints_revealed[1] == 3


def test_summary_and_retry_set() -> None:
    s = _session(3)
    s.feedback = {1: _fb(5), 2: _fb(2), 3: _fb(3)}
    assert s.overall_average == 3.33
    assert s.dimension_averages["depth"] == 3.33
    weak = s.retry_set()
    assert weak is not None
    assert [q.id for q in weak.questions] == [1, 2]
    assert [q.topic for q in weak.questions] == ["t2", "t3"]


def test_store_upserts_and_lists_sessions() -> None:
    store = Store(make_engine("sqlite://"), "me")
    s = _session(2)
    s.answers = {1: "my answer"}
    s.feedback = {1: _fb(4)}
    store.save_session(s)  # saved mid-session ...
    s.advance()
    s.advance()
    store.save_session(s)  # ... and again when finished: same row, updated
    loaded = store.load_session(s.id)
    assert loaded.id == s.id and loaded.is_finished
    assert loaded.answers == {1: "my answer"} and loaded.feedback[1].overall == 4
    summaries = store.list_sessions()
    assert len(summaries) == 1 and summaries[0].overall_average == 4.0
    assert summaries[0].id == s.id and summaries[0].answered == 1


def test_store_scopes_sessions_to_the_user() -> None:
    engine = make_engine("sqlite://")
    Store(engine, "alice").save_session(_session(1))
    bob = Store(engine, "bob")
    assert bob.list_sessions() == []
    alice_id = Store(engine, "alice").list_sessions()[0].id
    try:
        bob.load_session(alice_id)
    except KeyError:
        pass
    else:
        raise AssertionError("another user's session must not load")


def test_jd_handoff_renumbers_questions() -> None:
    analysis = JobAnalysis(
        title="Senior Frontend Engineer",
        seniority="Senior",
        domain="e-commerce",
        summary="s",
        skill_groups=[],
        likely_questions=[_q(7), _q(9)],
        prep_plan=[],
        questions_to_ask=[],
        red_flags=[],
    )
    qs = to_question_set(analysis)
    assert [q.id for q in qs.questions] == [1, 2]
    assert qs.difficulty == Difficulty.SENIOR
