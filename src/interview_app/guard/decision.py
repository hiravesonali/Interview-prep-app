from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Action = Literal["allow", "block", "redact"]
Layer = Literal["budget", "input_rules", "input_llm", "output", "openrouter"]


class InputKind(StrEnum):
    """What the text is; drives length limits and which checks apply."""

    ANSWER = "answer"
    JOB_DESCRIPTION = "job_description"
    TITLE = "title"
    FREE_TEXT = "free_text"


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    action: Action
    layer: Layer
    category: str
    reason: str
    text: str
    """Text to forward (possibly redacted). Empty when blocked."""
    matches: tuple[str, ...] = ()

    @classmethod
    def allow(cls, layer: Layer, text: str, reason: str = "passed") -> GuardDecision:
        return cls(True, "allow", layer, "ok", reason, text)

    @classmethod
    def block(
        cls, layer: Layer, category: str, reason: str, matches: tuple[str, ...] = ()
    ) -> GuardDecision:
        return cls(False, "block", layer, category, reason, "", matches)

    @classmethod
    def redact(
        cls, layer: Layer, category: str, reason: str, text: str, matches: tuple[str, ...] = ()
    ) -> GuardDecision:
        return cls(True, "redact", layer, category, reason, text, matches)
