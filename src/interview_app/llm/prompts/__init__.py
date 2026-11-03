"""Prompt loader. System prompts live as versioned Markdown files next to this module.

Keeping prompts out of Python keeps diffs readable and lets the Prompt Lab load
variants by name (e.g. "feedback/03_chain_of_thought").
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@cache
def load_prompt(name: str) -> str:
    """Return the prompt text for `name` (path relative to this folder, without .md)."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def list_prompts(subfolder: str) -> list[str]:
    """Names of all prompt files in a subfolder, sorted (used by the Prompt Lab)."""
    folder = PROMPTS_DIR / subfolder
    return sorted(f"{subfolder}/{p.stem}" for p in folder.glob("*.md"))


def render_prompt(name: str, **vars: str) -> str:
    """Load a prompt and substitute `{{key}}` placeholders (JSON braces stay untouched)."""
    text = load_prompt(name)
    for key, value in vars.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
