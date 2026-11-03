"""In-memory security log shown in the sidebar."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from interview_app.guard.decision import GuardDecision


@dataclass(frozen=True)
class LogEntry:
    time: datetime
    layer: str
    action: str
    category: str
    reason: str
    kind: str
    matches: tuple[str, ...]


@dataclass
class SecurityLog:
    entries: list[LogEntry] = field(default_factory=list)

    def record(self, decision: GuardDecision, kind: str) -> None:
        self.entries.append(
            LogEntry(
                time=datetime.now(),
                layer=decision.layer,
                action=decision.action,
                category=decision.category,
                reason=decision.reason,
                kind=kind,
                matches=decision.matches,
            )
        )

    @property
    def counts(self) -> Counter[str]:
        return Counter(e.action for e in self.entries)

    @property
    def fail_open_entries(self) -> list[LogEntry]:
        """Decisions where the LLM guard errored and let the input through."""
        return [e for e in self.entries if e.layer == "input_llm" and "fail-open" in e.reason]
