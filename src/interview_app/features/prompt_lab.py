"""Prompt Lab: run the same question + answer through several feedback prompt variants.

Variants run in parallel threads: each goes through the full guard pipeline, so the
security guard also runs per variant (cheap, and keeps the single choke point intact).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from interview_app.features.practice import evaluate_answer_detailed
from interview_app.guard import GuardBlocked, GuardPipeline, InputKind
from interview_app.llm.client import StructuredOutputError, Usage
from interview_app.llm.prompts import render_prompt
from interview_app.models import AnswerFeedback, JudgeVerdict, Question, QuestionType

SAMPLE_QUESTION = Question(
    id=1,
    type=QuestionType.TECHNICAL,
    topic="LLM evals",
    question=(
        "You changed the system prompt of a production summarisation feature. How would you "
        "decide whether the new prompt is better before shipping it?"
    ),
    strong_answer_covers=[
        "Define what 'better' means with concrete criteria (faithfulness, length, tone)",
        "Build a fixed eval set of real inputs, including hard cases",
        "Score with a mix of automatic checks and an LLM judge, calibrated against human labels",
        "Compare old vs new prompt on the same set; look at regressions, not only the average",
        "Ship behind a flag and monitor",
    ],
    hints=[
        "Think about what you would measure.",
        "You need the same inputs for both prompts.",
        "Automatic checks + LLM judge + a small human-labelled set, then a side-by-side "
        "comparison.",
    ],
)

SAMPLE_ANSWERS = {
    "Weak": (
        "I would try a few examples with the new prompt and if the summaries look good I'd "
        "ship it, then watch for complaints."
    ),
    "Mid": (
        "I'd collect maybe 50 real documents and run both prompts on them. Then I'd compare the "
        "outputs, probably with an LLM judge asking which summary is better, and ship if the new "
        "one wins most of the time."
    ),
    "Strong": (
        "First I'd pin down what better means for this feature: faithful to the source, within "
        "the length budget, and no missing key facts. Then I'd build an eval set of around 100 "
        "real inputs, deliberately including long documents and edge cases that caused complaints. "
        "I'd score both prompts on the same set: cheap automatic checks for length and format, an "
        "LLM judge for faithfulness that I'd calibrate against 20-30 human-labelled examples so I "
        "trust it, and a per-item diff so I can see regressions rather than just the average. If "
        "the new prompt wins and has no serious regressions, I'd ship it behind a flag to a small "
        "share of traffic and watch the same metrics in production before rolling out."
    ),
}


@dataclass(frozen=True)
class LabResult:
    technique: str
    feedback: AnswerFeedback | None
    usage: Usage | None
    error: str | None = None
    judge: JudgeVerdict | None = None
    judge_usage: Usage | None = None
    judge_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.feedback is not None


def run_comparison(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    answer: str,
    techniques: list[str],
    *,
    model: str | None = None,
    max_workers: int = 5,
) -> list[LabResult]:
    def one(technique: str) -> LabResult:
        try:
            result = evaluate_answer_detailed(
                pipe, role, question, answer, technique=technique, model=model
            )
        except GuardBlocked as err:
            return LabResult(technique, None, None, f"blocked by guard: {err.decision.reason}")
        except StructuredOutputError as err:
            return LabResult(technique, None, None, f"invalid output: {err}")
        except Exception as err:  # provider / network
            return LabResult(technique, None, None, f"{err.__class__.__name__}: {err}")
        return LabResult(technique, result.data, result.usage)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(one, techniques))


# ---------- LLM-as-a-judge ----------

_JUDGE_TEMPLATE = """Question type: {type}
Topic: {topic}
Interview question: {question}
Points a strong answer covers: {covers}

<candidate_answer>
{input}
</candidate_answer>

<feedback>
{feedback}
</feedback>"""


def judge_feedback(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    answer: str,
    feedback: AnswerFeedback,
    *,
    model: str | None = None,
) -> tuple[JudgeVerdict, Usage]:
    """Rate one feedback object against the judge rubric. The feedback is app-generated,
    so it goes into the template; only the candidate's answer passes through the guard."""
    template = (
        _JUDGE_TEMPLATE.replace("{type}", question.type.value)
        .replace("{topic}", question.topic)
        .replace("{question}", question.question)
        .replace("{covers}", "; ".join(question.strong_answer_covers) or "not specified")
        .replace("{feedback}", feedback.model_dump_json(indent=1, exclude_none=True))
    )
    result = pipe.structured(
        render_prompt("judge_feedback", role=role),
        answer,
        InputKind.ANSWER,
        JudgeVerdict,
        user_template=template,
        model=model,
        temperature=0.0,
        # Reasoning-style models (gpt-6-luna) spend completion tokens on thinking; 600 was
        # hit intermittently, which surfaces as a truncated JSON error.
        max_tokens=2000,
        purpose="judge",
    )
    return result.data, result.usage


def judge_results(
    pipe: GuardPipeline,
    role: str,
    question: Question,
    answer: str,
    results: list[LabResult],
    *,
    model: str | None = None,
    max_workers: int = 5,
) -> list[LabResult]:
    """Attach a judge verdict to every successful result (parallel, order preserved)."""

    def one(r: LabResult) -> LabResult:
        if r.feedback is None:
            return r
        try:
            verdict, usage = judge_feedback(pipe, role, question, answer, r.feedback, model=model)
        except GuardBlocked as err:
            return replace(r, judge_error=f"blocked by guard: {err.decision.reason}")
        except StructuredOutputError as err:
            return replace(r, judge_error=f"invalid output: {err}")
        except Exception as err:  # provider / network
            return replace(r, judge_error=f"{err.__class__.__name__}: {err}")
        return replace(r, judge=verdict, judge_usage=usage)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(one, results))
