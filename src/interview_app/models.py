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


class JudgeVerdict(BaseModel):
    """LLM-as-a-judge rating of one piece of feedback (Prompt Lab)."""

    accuracy: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    calibration: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    rationale: str = Field(description="At most three sentences")


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


# ---------- Feature 3: AI resume builder ----------


class ContactInfo(BaseModel):
    """Filled locally (regex over the raw text) and by the parser (name, location).

    Email and phone never reach the model: the input guard redacts them first.
    """

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list, description="LinkedIn, GitHub, portfolio")


class Bullet(BaseModel):
    id: str = Field(default="", description="Assigned by the app after parsing, e.g. 'e1b2'")
    text: str


class ExperienceEntry(BaseModel):
    title: str
    organisation: str
    dates: str = Field(description="As written, e.g. 'Mar 2021 - present'")
    location: str = ""
    bullets: list[Bullet]


class ProjectEntry(BaseModel):
    name: str
    description: str = Field(description="One line; empty if the resume only has bullets")
    technologies: list[str]
    bullets: list[Bullet]


class EducationEntry(BaseModel):
    degree: str
    institution: str
    dates: str = ""
    details: str = ""


class SkillCategory(BaseModel):
    name: str = Field(description="e.g. Languages, Frameworks, Cloud & tooling, AI/ML")
    skills: list[str]


class ParsedResume(BaseModel):
    """What the parser call returns: the resume as structured sections, nothing invented."""

    name: str = Field(description="Candidate's full name as written; empty if absent")
    location: str = Field(description="City / country if given, else empty")
    headline: str = Field(description="Current title or the resume's own headline")
    summary: str = Field(description="The resume's summary paragraph, or empty")
    experience: list[ExperienceEntry]
    projects: list[ProjectEntry]
    skills: list[SkillCategory]
    education: list[EducationEntry]
    certifications: list[str]


class ResumeProfile(ParsedResume):
    """A parsed resume plus the locally extracted contact details; what the app stores."""

    contact: ContactInfo = Field(default_factory=ContactInfo)


class TailoredBullet(BaseModel):
    text: str
    source_ids: list[str] = Field(
        description="Ids of the base-resume bullets this one is built from; empty = new claim"
    )
    reason: str = Field(default="", description="Why it changed; empty when kept as is")


class TailoredExperience(BaseModel):
    title: str
    organisation: str
    dates: str
    location: str = ""
    bullets: list[TailoredBullet]


class TailoredProject(BaseModel):
    name: str
    description: str = ""
    technologies: list[str]
    bullets: list[TailoredBullet]


KeywordStatus = Literal["present", "added", "missing"]


class KeywordMatch(BaseModel):
    keyword: str = Field(description="A skill, tool or requirement named in the JD")
    status: KeywordStatus = Field(
        description="present = already in the base resume; added = now surfaced from real "
        "evidence; missing = no evidence, left out"
    )
    note: str = Field(default="", description="Where it is covered, or why it is missing")


class TailoredResume(BaseModel):
    """The tailoring call's output. Education and certifications are copied from the base."""

    headline: str
    summary: str = Field(description="3-4 sentences aimed at this job")
    experience: list[TailoredExperience]
    projects: list[TailoredProject]
    skills: list[SkillCategory]
    keywords: list[KeywordMatch] = Field(description="10-20 JD requirements with their status")
    gaps: list[str] = Field(description="Requirements the candidate cannot honestly claim")
    changes_summary: str = Field(description="2-3 sentences on what was changed and why")


# ---------- Guard ----------


GuardCategory = Literal["ok", "prompt_injection", "off_topic", "harmful", "pii_or_secrets"]


class GuardVerdict(BaseModel):
    """Structured output of the LLM guard classifier."""

    allowed: bool
    category: GuardCategory
    reason: str = Field(description="One short sentence")
