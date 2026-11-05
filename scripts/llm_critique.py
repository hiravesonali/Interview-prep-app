"""Ask the main model to critique Hoot (usability, security, prompt engineering) → docs/.

    uv run python scripts/llm_critique.py            # ~$0.15, writes docs/llm_critique.md
    uv run python scripts/llm_critique.py --dry-run  # show what would be sent

Easy optional task: "Ask an LLM such as Claude or ChatGPT to critique your solution from the
usability, security, and prompt-engineering sides." The README, the guard, the prompts and the
practice feature go in as data through the normal pipeline (budget guard, cost ledger, output
guard); the result is committed under docs/ with a "What we changed" section added by hand.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from interview_app.config import get_settings
from interview_app.guard import GuardBlocked, GuardPipeline, InputKind, SecurityLog
from interview_app.llm.client import OpenRouterClient
from interview_app.llm.prompts import load_prompt
from interview_app.storage.store import open_store

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "interview_app"
FILES = [
    ROOT / "README.md",
    SRC / "guard" / "pipeline.py",
    SRC / "guard" / "input_guard.py",
    SRC / "guard" / "output_guard.py",
    SRC / "features" / "practice.py",
    SRC / "llm" / "prompts" / "question_generation.md",
    SRC / "llm" / "prompts" / "coach_guided.md",
    SRC / "llm" / "prompts" / "feedback" / "04_role_rubric.md",
    SRC / "llm" / "prompts" / "guard_classifier.md",
    SRC / "llm" / "prompts" / "judge_feedback.md",
    SRC / "llm" / "prompts" / "resume_tailor.md",
]
OUT = ROOT / "docs" / "llm_critique.md"


def bundle() -> str:
    parts = []
    for path in FILES:
        rel = path.relative_to(ROOT)
        parts.append(f'<file path="{rel}">\n{path.read_text(encoding="utf-8")}\n</file>')
    return "\n\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    settings = get_settings()
    model = args.model or settings.default_model
    material = bundle()
    print(f"model: {model} · {len(FILES)} files · {len(material):,} characters")
    if args.dry_run:
        return 0
    if not settings.has_api_key:
        print("No OPENROUTER_API_KEY in .env.", file=sys.stderr)
        return 1
    store = open_store(settings)
    client = OpenRouterClient(settings, store_tracker(store))
    pipe = GuardPipeline(
        client,
        settings,
        SecurityLog(),
        cost_today=store.cost_today,
        cost_today_all_users=store.cost_today_all_users,
        llm_guard_enabled=False,  # the only "user" text is the one-line request below
    )
    template = "Material to review:\n\n" + material.replace("{input}", "{ input }") + "\n\n{input}"
    try:
        result = pipe.chat(
            load_prompt("critique"),
            "Review the material above and write the critique.",
            InputKind.FREE_TEXT,
            user_template=template,
            model=model,
            temperature=0.3,
            max_tokens=12000,  # reasoning models spend completion tokens before writing
            purpose="critique",
        )
    except GuardBlocked as err:
        print(f"blocked: {err.decision.reason}", file=sys.stderr)
        return 1
    u = result.usage
    if not result.text.strip():
        print(
            f"empty reply (finish_reason={result.finish_reason!r}, "
            f"{u.completion_tokens} completion tokens, ${u.cost_usd:.4f}); nothing written",
            file=sys.stderr,
        )
        return 1
    header = (
        f"# LLM critique of Hoot\n\n"
        f"Generated {date.today().isoformat()} by `{u.model}` via `scripts/llm_critique.py` "
        f"({u.prompt_tokens:,} prompt + {u.completion_tokens:,} completion tokens, "
        f"${u.cost_usd:.4f}). Input: README, guard pipeline, prompts, practice feature.\n\n"
    )
    OUT.write_text(header + result.text.strip() + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} · ${u.cost_usd:.4f} · {u.latency_s:.1f}s")
    return 0


def store_tracker(store):
    from interview_app.llm.client import UsageTracker

    return UsageTracker(sink=store.record_usage)


if __name__ == "__main__":
    raise SystemExit(main())
