"""`Store`: every read and write the app does, scoped to one user.

Pages get it from `ui.state.store()`; scripts build one with `open_store(settings)`. Tests pass
an in-memory engine (`make_engine("sqlite://")`). Nothing else in the app touches SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from interview_app.config import Settings
from interview_app.features.practice import PracticeSession
from interview_app.storage.db import LabRunRow, SessionRow, get_engine
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


def open_store(settings: Settings, user_id: str = LOCAL_USER) -> Store:
    return Store(get_engine(settings.database_url), user_id)


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()
