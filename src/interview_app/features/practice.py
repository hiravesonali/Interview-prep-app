"""Feature 1: practice session — question generation, coaching, feedback, summary.

The session is a pydantic model so it serialises to JSON for history and survives
Streamlit reruns inside st.session_state. LLM calls go through the GuardPipeline only.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from interview_app.guard import GuardPipeline, InputKind
from interview_app.llm.client import StructuredResult
from interview_app.llm.prompts import load_prompt, render_prompt
from interview_app.models import AnswerFeedback, Difficulty, Question, QuestionSet, QuestionType

Mode = Literal["guided", "mock"]
Persona = Literal["strict", "neutral", "friendly"]
Style = Literal["concise", "detailed"]
DIMENSIONS = ("correctness", "depth", "structure", "communication")


class PracticeSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)  # storage key; stable across saves
    role: str
    mode: Mode
    question_set: QuestionSet
    feedback_technique: str
    source: Literal["generated", "jd"] = "generated"
    persona: Persona = "neutral"  # tone of the coach and the feedback (optional task)
    style: Style = "detailed"  # concise vs detailed responses (optional task)
    index: int = 0
    answers: dict[int, str] = Field(default_factory=dict)
    feedback: dict[int, AnswerFeedback] = Field(default_factory=dict)
    hints_revealed: dict[int, int] = Field(default_factory=dict)
    coaching: dict[int, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None

    # ----- navigation -----

    @property
    def questions(self) -> list[Question]:
        return self.question_set.questions

    @property
    def total(self) -> int:
        return len(self.questions)

    @property
    def current(self) -> Question:
        return self.questions[self.index]

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def is_last(self) -> bool:
        return self.index >= self.total - 1

    def reveal_hint(self, qid: int) -> int:
        n = min(self.hints_revealed.get(qid, 0) + 1, len(self.question_by_id(qid).hints))
        self.hints_revealed[qid] = n
        return n

    def question_by_id(self, qid: int) -> Question:
        return next(q for q in self.questions if q.id == qid)

    def advance(self) -> None:
        if self.is_last:
            self.finished_at = datetime.now()
        else:
            self.index += 1

    # ----- summary -----

    @property
    def dimension_averages(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for dim in DIMENSIONS:
            scores = [
                s.score for fb in self.feedback.values() for s in fb.scores if s.dimension == dim
            ]
            out[dim] = round(sum(scores) / len(scores), 2) if scores else 0.0
        return out

    @property
    def overall_average(self) -> float:
        if not self.feedback:
            return 0.0
        return round(sum(fb.overall for fb in self.feedback.values()) / len(self.feedback), 2)

    def weak_questions(self, threshold: int = 3) -> list[Question]:
        return [
            q
            for q in self.questions
            if q.id in self.feedback and self.feedback[q.id].overall <= threshold
        ]

    def retry_set(self) -> QuestionSet | None:
        weak = self.weak_questions()
        if not weak:
            return None
        questions = [q.model_copy(update={"id": i}) for i, q in enumerate(weak, 1)]
        return QuestionSet(
            role=self.role, difficulty=self.question_set.difficulty, questions=questions
        )


# ----- LLM-backed operations -----


def build_system_prompt(
    name: str, role: str, *, persona: Persona | None = None, style: Style | None = None
) -> str:
    """The task prompt plus optional persona and length blocks from `prompts/style/`.

    The blocks are appended by code so the feedback variants (the Prompt Lab's subject) stay
    untouched; the Lab passes neither and compares the bare techniques.
    """
    parts = [render_prompt(name, role=role)]
    if persona:
        parts.append(load_prompt(f"style/persona_{persona}"))
    if style:
        parts.append(load_prompt(f"style/style_{style}"))
    return "\n\n".join(parts)


_GENERATION_TEMPLATE = """Role: {input}
Difficulty: {difficulty}
Number of questions: {count}
Question types to include: {types}
Topics to draw from: {topics}

Return the QuestionSet JSON with `role` = the role above and `difficulty` = "{difficulty}"."""


def generate_question_set(
    pipe: GuardPipeline,
    role: str,
    *,
    difficulty: Difficulty,
    types: list[QuestionType],
    topics: list[str],
    count: int = 10,
    model: str | None = None,
) -> QuestionSet:
    template = (
        _GENERATION_TEMPLATE.replace("{difficulty}", difficulty.value)
        .replace("{count}", str(count))
        .replace("{types}", ", ".join(t.value for t in types))
        .replace("{topics}", ", ".join(topics) if topics else "choose typical topics for the role")
    )
    result = pipe.structured(
        render_prompt("question_generation", role=role),
        role,
        InputKind.TITLE,
        QuestionSet,
        user_template=template,
        model=model,
        temperature=0.6,
        max_tokens=600 * count + 500,
        purpose="question_generation",
    )
    qs = result.data
    # Normalise ids and trim in case the model over-delivers.
    qs.questions = [q.model_copy(update={"id": i}) for i, q in enumerate(qs.questions[:count], 1)]
    return qs


_COACH_TEMPLATE = """Question type: {type}
Topic: {topic}
Interview question: {question}

Candidate's note (may be empty): {input}"""


def coach_stream(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    note: str = "",
    model: str | None = None,
    *,
    persona: Persona | None = None,
    style: Style | None = None,
) -> Iterator[str]:
    template = (
        _COACH_TEMPLATE.replace("{type}", question.type.value)
        .replace("{topic}", question.topic)
        .replace("{question}", question.question)
    )
    return pipe.stream(
        build_system_prompt("coach_guided", role, persona=persona, style=style),
        note.strip() or "(none)",
        InputKind.FREE_TEXT,
        user_template=template,
        model=model,
        purpose="coach",
    )


_FEEDBACK_TEMPLATE = """Question type: {type}
Topic: {topic}
Interview question: {question}
Points a strong answer covers: {covers}

<candidate_answer>
{input}
</candidate_answer>"""


def evaluate_answer_detailed(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    answer: str,
    *,
    technique: str = "feedback/01_zero_shot",
    model: str | None = None,
    persona: Persona | None = None,
    style: Style | None = None,
) -> StructuredResult[AnswerFeedback]:
    """Like evaluate_answer but also returns raw output and usage (used by the Prompt Lab)."""
    template = (
        _FEEDBACK_TEMPLATE.replace("{type}", question.type.value)
        .replace("{topic}", question.topic)
        .replace("{question}", question.question)
        .replace("{covers}", "; ".join(question.strong_answer_covers))
    )
    result = pipe.structured(
        build_system_prompt(technique, role, persona=persona, style=style),
        answer,
        InputKind.ANSWER,
        AnswerFeedback,
        user_template=template,
        model=model,
        purpose=f"feedback:{technique.rsplit('/', 1)[-1]}",
    )
    return result


def evaluate_answer(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    answer: str,
    *,
    technique: str = "feedback/01_zero_shot",
    model: str | None = None,
    persona: Persona | None = None,
    style: Style | None = None,
) -> AnswerFeedback:
    return evaluate_answer_detailed(
        pipe, role, question, answer, technique=technique, model=model, persona=persona, style=style
    ).data
