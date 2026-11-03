"""Pydantic schemas shared by the LLM layer, the guard and the UI.

Every structured LLM call targets one of these models: the JSON schema is sent to
OpenRouter as `response_format`, and the response is validated back into the model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Difficulty(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class QuestionType(StrEnum):
    TECHNICAL = "technical"
    SYSTEM_DESIGN = "system_design"
    BEHAVIOURAL = "behavioural"
    ROLE_SPECIFIC = "role_specific"


# ---------- Feature 1: practice session ----------


class Question(BaseModel):
    id: int = Field(description="1-based position in the set")
    type: QuestionType
    topic: str = Field(description="Short topic label, e.g. 'React state management'")
    question: str
    strong_answer_covers: list[str] = Field(description="Key points a strong answer includes")
    hints: list[str] = Field(description="3 progressive hints, vague to specific", min_length=1)


class QuestionSet(BaseModel):
    role: str
    difficulty: Difficulty
    questions: list[Question]


class DimensionScore(BaseModel):
    dimension: Literal["correctness", "depth", "structure", "communication"]
    score: int = Field(ge=1, le=5)
    comment: str


class AnswerFeedback(BaseModel):
    analysis: str | None = Field(
        default=None,
        description="Chain-of-thought style reasoning, filled only by prompts that ask for it",
    )
    scores: list[DimensionScore]
    overall: int = Field(ge=1, le=5)
    strengths: list[str]
    gaps: list[str]
    model_answer: str
    follow_up_question: str


# ---------- Feature 2: job description analysis ----------


class SkillGroup(BaseModel):
    name: str = Field(description="e.g. Languages, Frameworks, Infrastructure, AI/ML, Soft skills")
    must_have: list[str]
    nice_to_have: list[str]


class PrepDay(BaseModel):
    day: int
    focus: str
    tasks: list[str]


class JobAnalysis(BaseModel):
    title: str
    seniority: str
    domain: str
    summary: str = Field(description="3-4 sentence role snapshot")
    skill_groups: list[SkillGroup]
    likely_questions: list[Question]
    prep_plan: list[PrepDay]
    questions_to_ask: list[str]
    red_flags: list[str]


# ---------- Guard ----------


GuardCategory = Literal["ok", "prompt_injection", "off_topic", "harmful", "pii_or_secrets"]


class GuardVerdict(BaseModel):
    """Structured output of the LLM guard classifier."""

    allowed: bool
    category: GuardCategory
    reason: str = Field(description="One short sentence")
