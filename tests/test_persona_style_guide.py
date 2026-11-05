"""Interviewer persona, response style (prompt blocks appended by code) and interviewer guide."""

from __future__ import annotations

from interview_app.config import Settings
from interview_app.features.interviewer_guide import generate_guide
from interview_app.features.practice import PracticeSession, build_system_prompt, evaluate_answer
from interview_app.guard import GuardPipeline, SecurityLog
from interview_app.llm.client import OpenRouterClient, StructuredResult, Usage
from interview_app.llm.prompts import list_prompts, render_prompt
from interview_app.models import (
    AnswerFeedback,
    Difficulty,
    DimensionScore,
    GuideSection,
    InterviewerGuide,
    Question,
    QuestionSet,
    QuestionType,
    RubricAnchor,
)


class FakeStructuredClient(OpenRouterClient):
    def __init__(self, data):
        super().__init__(Settings(openrouter_api_key="t"))
        self.data = data
        self.systems: list[str] = []

    def chat_structured(self, messages, schema, **kw):  # type: ignore[override]
        self.systems.append(messages[0]["content"])
        return StructuredResult(self.data, "{}", Usage("m", 1, 1, 0.0, 0.1))


def _pipe(data):
    client = FakeStructuredClient(data)
    return GuardPipeline(client, client.settings, SecurityLog(), llm_guard_enabled=False), client


def _question() -> Question:
    return Question(
        id=1,
        type=QuestionType.TECHNICAL,
        topic="t",
        question="Q?",
        strong_answer_covers=["a"],
        hints=["h1", "h2", "h3"],
    )


def _feedback() -> AnswerFeedback:
    return AnswerFeedback(
        scores=[
            DimensionScore(dimension=d, score=3, comment="c")
            for d in ("correctness", "depth", "structure", "communication")
        ],
        overall=3,
        strengths=["s"],
        gaps=["g"],
        model_answer="m",
        follow_up_question="f",
    )


def test_style_blocks_exist_for_every_option() -> None:
    names = list_prompts("style")
    for option in ("persona_strict", "persona_neutral", "persona_friendly"):
        assert f"style/{option}" in names
    for option in ("style_concise", "style_detailed"):
        assert f"style/{option}" in names


def test_bare_technique_prompt_is_untouched_without_options() -> None:
    bare = render_prompt("feedback/04_role_rubric", role="AI Engineer")
    assert build_system_prompt("feedback/04_role_rubric", "AI Engineer") == bare


def test_persona_and_style_are_appended_after_the_technique() -> None:
    text = build_system_prompt(
        "feedback/04_role_rubric", "AI Engineer", persona="strict", style="concise"
    )
    bare = render_prompt("feedback/04_role_rubric", role="AI Engineer")
    assert text.startswith(bare)
    assert text.index("Interviewer persona: STRICT") < text.index("Response length: CONCISE")


def test_evaluate_answer_sends_the_blocks_to_the_model() -> None:
    pipe, client = _pipe(_feedback())
    evaluate_answer(
        pipe, "AI Engineer", _question(), "my answer", persona="friendly", style="concise"
    )
    assert "Interviewer persona: FRIENDLY" in client.systems[0]
    assert "Response length: CONCISE" in client.systems[0]
    evaluate_answer(pipe, "AI Engineer", _question(), "my answer")  # the Lab's bare call
    assert "Interviewer persona" not in client.systems[1]


def test_session_defaults_keep_old_saved_sessions_valid() -> None:
    qs = QuestionSet(role="r", difficulty=Difficulty.MID, questions=[_question()])
    old = PracticeSession(role="r", mode="guided", question_set=qs, feedback_technique="x")
    restored = PracticeSession.model_validate(old.model_dump(mode="json"))
    assert (restored.persona, restored.style) == ("neutral", "detailed")


def test_generate_guide_puts_role_and_skills_in_the_prompt() -> None:
    guide = InterviewerGuide(
        role="Backend Engineer",
        seniority="senior",
        hiring_bar="Owns a service end to end.",
        rubric=[
            RubricAnchor(dimension=d, looks_like_1="1", looks_like_3="3", looks_like_5="5")
            for d in ("correctness", "depth", "structure", "communication")
        ],
        sections=[
            GuideSection(kind=k, green_flags=["g"], red_flags=["r"], probing_questions=["p"])
            for k in ("technical", "behavioural")
        ],
        decision_rules=["two 2s = no hire"],
    )
    pipe, client = _pipe(guide)
    result = generate_guide(pipe, "Backend Engineer", "senior", skills=["Kafka", "Postgres"])
    assert result.data.sections[1].kind == "behavioural"
    assert "Backend Engineer loop at senior level" in client.systems[0]
