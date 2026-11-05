"""Interviewer guidelines: structured evaluation criteria for a role and seniority.

Optional course task ("ask the LLM to create structured evaluation criteria for technical and
behavioural interviews"). One structured call; the result is the candidate's look at the other
side of the table, shown in the JD analyzer and on the practice summary.
"""

from __future__ import annotations

from interview_app.guard import GuardPipeline, InputKind
from interview_app.llm.client import StructuredResult
from interview_app.llm.prompts import render_prompt
from interview_app.models import InterviewerGuide

_TEMPLATE = """Role: {input}
Seniority: {seniority}
Skills the loop should probe (may be empty): {skills}"""


def generate_guide(
    pipe: GuardPipeline,
    role: str,
    seniority: str,
    *,
    skills: list[str] | None = None,
    model: str | None = None,
) -> StructuredResult[InterviewerGuide]:
    level = pipe.check_input(seniority, InputKind.TITLE).text if seniority.strip() else "mid"
    skill_text = ", ".join(skills or [])[:800] or "none listed"
    template = _TEMPLATE.replace("{seniority}", level).replace("{skills}", skill_text)
    return pipe.structured(
        render_prompt("interviewer_guide", role=role, seniority=level),
        role,
        InputKind.TITLE,
        InterviewerGuide,
        user_template=template,
        model=model,
        max_tokens=6000,
        purpose="interviewer_guide",
    )
