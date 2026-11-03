"""Feature 2: job-description analysis (chain-of-thought prompt + structured output)."""

from __future__ import annotations

from interview_app.guard import GuardPipeline, InputKind
from interview_app.llm.client import StructuredResult
from interview_app.llm.prompts import render_prompt
from interview_app.models import Difficulty, JobAnalysis, QuestionSet

_USER_TEMPLATE = """Candidate's target title (may be empty): {title}
Preparation plan length: {days} days

<job_description>
{input}
</job_description>"""


def analyze_job_description(
    pipe: GuardPipeline,
    jd_text: str,
    *,
    target_title: str = "",
    plan_days: int = 7,
    model: str | None = None,
) -> StructuredResult[JobAnalysis]:
    title = ""
    if target_title.strip():
        title = pipe.check_input(target_title, InputKind.TITLE).text
    system = render_prompt("jd_analysis", plan_days=plan_days)
    template = _USER_TEMPLATE.replace("{title}", title).replace("{days}", str(plan_days))
    return pipe.structured(
        system,
        jd_text,
        InputKind.JOB_DESCRIPTION,
        JobAnalysis,
        user_template=template,
        model=model,
        max_tokens=10000,  # 10 questions with hints + a 14-day plan is a large JSON document
        purpose="jd_analysis",
    )


def to_question_set(analysis: JobAnalysis) -> QuestionSet:
    """Hand-off to the practice feature: the JD's likely questions as a practice set."""
    difficulty = {
        "junior": Difficulty.JUNIOR,
        "mid": Difficulty.MID,
    }.get(analysis.seniority.lower(), Difficulty.SENIOR)
    questions = [q.model_copy(update={"id": i}) for i, q in enumerate(analysis.likely_questions, 1)]
    return QuestionSet(role=analysis.title, difficulty=difficulty, questions=questions)
