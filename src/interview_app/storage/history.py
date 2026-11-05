"""List rows: what the dashboard and the resume builder show per saved item (see `store.py`)."""

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


@dataclass(frozen=True)
class ResumeSummary:
    id: str
    name: str
    headline: str
    created_at: datetime


@dataclass(frozen=True)
class TailoredSummary:
    id: str
    base_resume_id: str
    job_title: str
    company: str
    match_score: int
    created_at: datetime

    @property
    def label(self) -> str:
        return f"{self.job_title} · {self.company}" if self.company else self.job_title
