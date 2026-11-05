"""`Store`: every read and write the app does, scoped to one user.

Pages get it from `ui.state.store()`; scripts build one with `open_store(settings)`. Tests pass
an in-memory engine (`make_engine("sqlite://")`). Nothing else in the app touches SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from interview_app.config import Settings
from interview_app.features.practice import PracticeSession
from interview_app.guard.log import LogEntry
from interview_app.llm.client import Usage
from interview_app.storage.db import (
    LabRunRow,
    SecurityEventRow,
    SessionRow,
    UsageEventRow,
    get_engine,
)
from interview_app.storage.history import SessionSummary
from interview_app.storage.prompt_lab import LabRecord

LOCAL_USER = "local"  # user id when the app runs without sign-in


class Store:
    def __init__(self, engine: Engine, user_id: str = LOCAL_USER) -> None:
        self.engine = engine
        self.user_id = user_id

    # ----- practice sessions -----

    def save_session(self, session: PracticeSession) -> str:
        """Insert or update (the page saves after every answer). Returns the session id."""
        with Session(self.engine) as db, db.begin():
            row = db.get(SessionRow, session.id)
            if row is None:
                row = SessionRow(id=session.id, user_id=self.user_id)
                db.add(row)
            row.role = session.role
            row.mode = session.mode
            row.started_at = session.started_at
            row.finished_at = session.finished_at
            row.questions = session.total
            row.answered = len(session.answers)
            row.overall_average = session.overall_average
            row.payload = session.model_dump(mode="json")
        return session.id

    def load_session(self, session_id: str) -> PracticeSession:
        with Session(self.engine) as db:
            row = db.get(SessionRow, session_id)
            if row is None or row.user_id != self.user_id:
                raise KeyError(session_id)
            return PracticeSession.model_validate(row.payload)

    def list_sessions(self, limit: int = 10) -> list[SessionSummary]:
        stmt = (
            select(SessionRow)
            .where(SessionRow.user_id == self.user_id)
            .order_by(SessionRow.started_at.desc())
            .limit(limit)
        )
        with Session(self.engine) as db:
            return [
                SessionSummary(
                    id=r.id,
                    role=r.role,
                    mode=r.mode,
                    started_at=r.started_at,
                    questions=r.questions,
                    answered=r.answered,
                    overall_average=r.overall_average,
                )
                for r in db.scalars(stmt)
            ]

    # ----- prompt lab -----

    def append_lab_records(self, records: list[LabRecord]) -> None:
        with Session(self.engine) as db, db.begin():
            db.add_all(
                LabRunRow(
                    user_id=self.user_id,
                    created_at=_parse_time(r.time),
                    technique=r.technique,
                    model=r.model,
                    rating=r.rating,
                    judge_overall=r.judge_overall,
                    payload=asdict(r),
                )
                for r in records
            )

    def load_lab_records(self) -> list[LabRecord]:
        stmt = select(LabRunRow).where(LabRunRow.user_id == self.user_id).order_by(LabRunRow.id)
        with Session(self.engine) as db:
            return [LabRecord(**r.payload) for r in db.scalars(stmt)]

    # ----- audit trail and spend (sinks for SecurityLog / UsageTracker, see ui.state) -----

    def record_security_event(self, entry: LogEntry) -> None:
        with Session(self.engine) as db, db.begin():
            db.add(
                SecurityEventRow(
                    user_id=self.user_id,
                    created_at=entry.time,
                    layer=entry.layer,
                    action=entry.action,
                    category=entry.category,
                    kind=entry.kind,
                    reason=entry.reason[:1000],
                    matches=list(entry.matches),
                )
            )

    def record_usage(self, usage: Usage, *, at: datetime | None = None) -> None:
        with Session(self.engine) as db, db.begin():
            db.add(
                UsageEventRow(
                    user_id=self.user_id,
                    created_at=at or datetime.now(),
                    model=usage.model,
                    purpose=usage.purpose,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cost_usd=usage.cost_usd,
                )
            )

    def cost_today(self) -> float:
        """USD spent by this user since local midnight, every model call included (guard too)."""
        return self._cost_since_midnight(UsageEventRow.user_id == self.user_id)

    def cost_today_all_users(self) -> float:
        """USD spent by everyone since local midnight: the global cap for a public deployment."""
        return self._cost_since_midnight()

    def _cost_since_midnight(self, *conditions) -> float:
        start = datetime.combine(datetime.now().date(), time.min)
        stmt = select(func.coalesce(func.sum(UsageEventRow.cost_usd), 0.0)).where(
            UsageEventRow.created_at >= start, *conditions
        )
        with Session(self.engine) as db:
            return float(db.scalar(stmt) or 0.0)


def open_store(settings: Settings, user_id: str = LOCAL_USER) -> Store:
    return Store(get_engine(settings.database_url), user_id)


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()
