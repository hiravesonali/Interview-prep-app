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
from interview_app.features.resume import BaseResume, TailoredResumeDoc, match_scores
from interview_app.guard.log import LogEntry
from interview_app.llm.client import Usage
from interview_app.storage.db import (
    LabRunRow,
    ResumeRow,
    SecurityEventRow,
    SessionRow,
    TailoredResumeRow,
    UsageEventRow,
    get_engine,
)
from interview_app.storage.history import ResumeSummary, SessionSummary, TailoredSummary
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

    # ----- resume builder -----

    def save_resume(self, resume: BaseResume) -> str:
        with Session(self.engine) as db, db.begin():
            row = db.get(ResumeRow, resume.id)
            if row is None:
                row = ResumeRow(id=resume.id, user_id=self.user_id)
                db.add(row)
            elif row.user_id != self.user_id:
                raise KeyError(resume.id)
            row.name = resume.name
            row.headline = resume.profile.headline
            row.created_at = resume.created_at
            row.payload = resume.model_dump(mode="json")
        return resume.id

    def load_resume(self, resume_id: str) -> BaseResume:
        with Session(self.engine) as db:
            row = db.get(ResumeRow, resume_id)
            if row is None or row.user_id != self.user_id:
                raise KeyError(resume_id)
            return BaseResume.model_validate(row.payload)

    def list_resumes(self) -> list[ResumeSummary]:
        stmt = (
            select(ResumeRow)
            .where(ResumeRow.user_id == self.user_id)
            .order_by(ResumeRow.created_at.desc())
        )
        with Session(self.engine) as db:
            return [
                ResumeSummary(id=r.id, name=r.name, headline=r.headline, created_at=r.created_at)
                for r in db.scalars(stmt)
            ]

    def delete_resume(self, resume_id: str) -> None:
        """Deletes the base resume only; tailored copies keep their profile snapshot."""
        with Session(self.engine) as db, db.begin():
            row = db.get(ResumeRow, resume_id)
            if row is not None and row.user_id == self.user_id:
                db.delete(row)

    def save_tailored(self, doc: TailoredResumeDoc) -> str:
        with Session(self.engine) as db, db.begin():
            row = db.get(TailoredResumeRow, doc.id)
            if row is None:
                row = TailoredResumeRow(id=doc.id, user_id=self.user_id)
                db.add(row)
            elif row.user_id != self.user_id:
                raise KeyError(doc.id)
            row.base_resume_id = doc.base_resume_id
            row.job_title = doc.job_title
            row.company = doc.company
            row.match_score = match_scores(doc.result)[1]
            row.created_at = doc.created_at
            row.payload = doc.model_dump(mode="json")
        return doc.id

    def load_tailored(self, doc_id: str) -> TailoredResumeDoc:
        with Session(self.engine) as db:
            row = db.get(TailoredResumeRow, doc_id)
            if row is None or row.user_id != self.user_id:
                raise KeyError(doc_id)
            return TailoredResumeDoc.model_validate(row.payload)

    def list_tailored(self) -> list[TailoredSummary]:
        stmt = (
            select(TailoredResumeRow)
            .where(TailoredResumeRow.user_id == self.user_id)
            .order_by(TailoredResumeRow.created_at.desc())
        )
        with Session(self.engine) as db:
            return [
                TailoredSummary(
                    id=r.id,
                    base_resume_id=r.base_resume_id,
                    job_title=r.job_title,
                    company=r.company,
                    match_score=r.match_score,
                    created_at=r.created_at,
                )
                for r in db.scalars(stmt)
            ]

    def delete_tailored(self, doc_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            row = db.get(TailoredResumeRow, doc_id)
            if row is not None and row.user_id == self.user_id:
                db.delete(row)

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
