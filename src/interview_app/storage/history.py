"""Local JSON history of finished practice sessions (data/sessions/*.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from interview_app.features.practice import PracticeSession


@dataclass(frozen=True)
class SessionSummary:
    path: Path
    role: str
    mode: str
    started_at: datetime
    questions: int
    answered: int
    overall_average: float


def sessions_dir(data_dir: Path) -> Path:
    d = data_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(session: PracticeSession, data_dir: Path) -> Path:
    stamp = session.started_at.strftime("%Y%m%d-%H%M%S")
    slug = "".join(ch if ch.isalnum() else "-" for ch in session.role.lower())[:40].strip("-")
    path = sessions_dir(data_dir) / f"{stamp}-{slug or 'session'}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_session(path: Path) -> PracticeSession:
    return PracticeSession.model_validate_json(path.read_text(encoding="utf-8"))


def list_sessions(data_dir: Path, limit: int = 10) -> list[SessionSummary]:
    out: list[SessionSummary] = []
    for path in sorted(sessions_dir(data_dir).glob("*.json"), reverse=True)[:limit]:
        try:
            s = load_session(path)
        except (ValueError, json.JSONDecodeError):
            continue
        out.append(
            SessionSummary(
                path=path,
                role=s.role,
                mode=s.mode,
                started_at=s.started_at,
                questions=s.total,
                answered=len(s.answers),
                overall_average=s.overall_average,
            )
        )
    return out
