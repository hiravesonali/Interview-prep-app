"""Practice-session history: the summary row shown on the dashboard (storage is in `store.py`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SessionSummary:
    id: str
    role: str
    mode: str
    started_at: datetime
    questions: int
    answered: int
    overall_average: float
