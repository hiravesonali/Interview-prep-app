"""Run the Prompt Lab comparison from the command line and record the results.

    uv run python scripts/run_prompt_lab.py                     # 5 techniques x 3 answers + judge
    uv run python scripts/run_prompt_lab.py --no-judge
    uv run python scripts/run_prompt_lab.py --temperature-sweep # zero-shot at T=0.2 / 1.0, x2 each
    uv run python scripts/run_prompt_lab.py --style-sweep       # grader: concise vs detailed
    uv run python scripts/run_prompt_lab.py --dry-run           # print the plan, call nothing

Results are appended to the database (same store as the Lab page, so the leaderboard
shows them) and a Markdown table is printed for the README. Human ratings stay empty: those are
added in the Lab UI.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from interview_app.config import AVAILABLE_MODELS, get_settings
from interview_app.features.practice import evaluate_answer_detailed
from interview_app.features.prompt_lab import (
    SAMPLE_ANSWERS,
    SAMPLE_QUESTION,
    LabResult,
    judge_feedback,
    judge_results,
    run_comparison,
)
from interview_app.guard import GuardPipeline, SecurityLog
from interview_app.llm.client import OpenRouterClient
from interview_app.llm.prompts import list_prompts
from interview_app.storage.prompt_lab import LabRecord, now_iso
from interview_app.storage.store import open_store

ROLE = "AI Engineer"


def _label(technique: str) -> str:
    return technique.rsplit("/", 1)[-1]


def comparison(pipe: GuardPipeline, model: str, judge_model: str | None) -> None:
    techniques = list_prompts("feedback")
    per_technique: dict[str, list[LabResult]] = defaultdict(list)
    matrix: dict[str, dict[str, str]] = defaultdict(dict)
    for level, answer in SAMPLE_ANSWERS.items():
        print(f"\n== {level} answer ==")
        results = run_comparison(pipe, ROLE, SAMPLE_QUESTION, answer, techniques, model=model)
        if judge_model:
            results = judge_results(pipe, ROLE, SAMPLE_QUESTION, answer, results, model=judge_model)
        records = []
        for r in results:
            if not r.ok or r.feedback is None or r.usage is None:
                print(f"  {_label(r.technique):20} FAILED: {r.error}")
                matrix[r.technique][level] = "err"
                continue
            judge = (
                f" judge {r.judge.overall}" if r.judge else (" judge-err" if r.judge_error else "")
            )
            print(
                f"  {_label(r.technique):20} overall {r.feedback.overall}{judge} "
                f"${r.usage.cost_usd:.4f} {r.usage.total_tokens:5d} tok {r.usage.latency_s:5.1f}s"
            )
            per_technique[r.technique].append(r)
            matrix[r.technique][level] = f"{r.feedback.overall}" + (
                f" / j{r.judge.overall}" if r.judge else ""
            )
            records.append(
                LabRecord(
                    time=now_iso(),
                    technique=r.technique,
                    model=r.usage.model,
                    question=SAMPLE_QUESTION.question[:120],
                    answer_preview=answer[:120],
                    overall=r.feedback.overall,
                    cost_usd=r.usage.cost_usd,
                    latency_s=round(r.usage.latency_s, 2),
                    tokens=r.usage.total_tokens,
                    note=f"script · sample answer: {level}",
                    judge_overall=r.judge.overall if r.judge else None,
                    judge_model=r.judge_usage.model if r.judge_usage else "",
                )
            )
        open_store(pipe.settings).append_lab_records(records)

    print("\n### Scores per sample answer (feedback's overall score / judge score)\n")
    levels = list(SAMPLE_ANSWERS)
    print("| Technique | " + " | ".join(levels) + " |")
    print("|---|" + "---|" * len(levels))
    for t in techniques:
        print(f"| {_label(t)} | " + " | ".join(matrix[t].get(lv, "-") for lv in levels) + " |")

    print("\n### Averages over the three answers\n")
    print("| Technique | Judge avg | Cost / run | Latency | Tokens |")
    print("|---|---|---|---|---|")
    for t in techniques:
        rs = per_technique[t]
        if not rs:
            continue
        judged = [r.judge.overall for r in rs if r.judge]
        j = f"{sum(judged) / len(judged):.2f}" if judged else "-"
        cost = sum(r.usage.cost_usd for r in rs) / len(rs)
        lat = sum(r.usage.latency_s for r in rs) / len(rs)
        tok = sum(r.usage.total_tokens for r in rs) / len(rs)
        print(f"| {_label(t)} | {j} | ${cost:.4f} | {lat:.1f}s | {tok:,.0f} |")


def temperature_sweep(pipe: GuardPipeline, model: str) -> None:
    """Easy optional task: tune one setting and compare. Zero-shot feedback on the Mid answer."""
    technique = "feedback/01_zero_shot"
    answer = SAMPLE_ANSWERS["Mid"]
    print("\n### Temperature sweep (zero-shot, Mid answer, 2 runs each)\n")
    print("| T | Run | Overall | correctness/depth/structure/communication | Gaps named |")
    print("|---|---|---|---|---|")
    for temp in (0.2, 1.0):
        pipe.overrides.temperature = temp
        for run in (1, 2):
            r = run_comparison(pipe, ROLE, SAMPLE_QUESTION, answer, [technique], model=model)[0]
            if r.feedback is None:
                print(f"| {temp} | {run} | error | {r.error} | |")
                continue
            dims = "/".join(str(s.score) for s in r.feedback.scores)
            gaps = "; ".join(g[:40] for g in r.feedback.gaps)
            print(f"| {temp} | {run} | {r.feedback.overall} | {dims} | {gaps} |")
    pipe.overrides.temperature = None


def style_sweep(pipe: GuardPipeline, model: str, judge_model: str | None) -> None:
    """Easy optional task: concise vs detailed responses, same grader, all three answers."""
    technique = "feedback/04_role_rubric"
    print("\n### Response style sweep (role + rubric, no persona block)\n")
    print("| Style | Answer | Overall | Judge | Tokens | Cost | Latency | Words in feedback |")
    print("|---|---|---|---|---|---|---|---|")
    for style in ("concise", "detailed"):
        for level, answer in SAMPLE_ANSWERS.items():
            r = evaluate_answer_detailed(
                pipe, ROLE, SAMPLE_QUESTION, answer, technique=technique, model=model, style=style
            )
            fb, u = r.data, r.usage
            judge = "-"
            if judge_model:
                verdict, _ = judge_feedback(
                    pipe, ROLE, SAMPLE_QUESTION, answer, fb, model=judge_model
                )
                judge = str(verdict.overall)
            words = len(fb.model_dump_json(exclude_none=True).split())
            print(
                f"| {style} | {level} | {fb.overall} | {judge} | {u.total_tokens:,} | "
                f"${u.cost_usd:.4f} | {u.latency_s:.1f}s | {words} |"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=None, help="feedback model (default: DEFAULT_MODEL)")
    ap.add_argument("--judge-model", default=None, help="default: first course model != model")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--temperature-sweep", action="store_true")
    ap.add_argument("--style-sweep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    model = args.model or settings.default_model
    judge_model = None
    if not args.no_judge:
        judge_model = args.judge_model or next(m for m in AVAILABLE_MODELS if m != model)
    print(f"feedback: {model} · judge: {judge_model or 'off'} · guard: {settings.guard_model}")
    if args.dry_run:
        n = len(list_prompts("feedback")) * len(SAMPLE_ANSWERS)
        if args.temperature_sweep:
            n = 4
        elif args.style_sweep:
            n = 2 * len(SAMPLE_ANSWERS)
        print(f"would make {n} feedback calls" + (f" + {n} judge calls" if judge_model else ""))
        return 0
    if not settings.has_api_key:
        print("No OPENROUTER_API_KEY in .env.", file=sys.stderr)
        return 1

    client = OpenRouterClient(settings)
    pipe = GuardPipeline(client, settings, SecurityLog())
    if args.temperature_sweep:
        temperature_sweep(pipe, model)
    elif args.style_sweep:
        style_sweep(pipe, model, judge_model)
    else:
        comparison(pipe, model, judge_model)
    t = client.tracker
    print(f"\n{len(t.calls)} calls · {t.total_tokens:,} tokens · ${t.total_cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
