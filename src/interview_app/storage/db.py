"""Database engine and tables (SQLAlchemy 2.x).

One code path for every environment: `DATABASE_URL` picks the engine.
  local  sqlite:///data/hoot.db        (file, zero setup)
  tests  sqlite://                     (in memory, offline)
  prod   postgresql+psycopg://...      (hosted Postgres, e.g. Neon)

Schema style is "document with index": each table has a few scalar columns for listing and
filtering plus one JSON column holding the full pydantic dump. The pydantic models in
`features/` and `models.py` stay the source of truth; the table shape rarely changes, so there
are no migrations yet (`init_db` creates missing tables, which is enough until a column changes).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, DateTime, Engine, Float, Integer, LargeBinary, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    """One practice session; `payload` is the whole `PracticeSession`, re-saved per answer."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    questions: Mapped[int] = mapped_column(Integer)
    answered: Mapped[int] = mapped_column(Integer)
    overall_average: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class LabRunRow(Base):
    """One Prompt Lab technique run; `payload` is the `LabRecord` as a dict."""

    __tablename__ = "prompt_lab_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    technique: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_overall: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class SecurityEventRow(Base):
    """One guard decision (audit trail; the sidebar shows the in-memory log of the current run)."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    layer: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    matches: Mapped[list[str]] = mapped_column(JSON)


class UsageEventRow(Base):
    """One model call's tokens and cost; `cost_today` sums these for the daily spend cap."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    model: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)


class ResumeRow(Base):
    """One uploaded base resume; `payload` is the `BaseResume` (raw text + parsed profile)."""

    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class TailoredResumeRow(Base):
    """One tailored resume per job application; `payload` is the `TailoredResumeDoc`."""

    __tablename__ = "tailored_resumes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(320), index=True)
    base_resume_id: Mapped[str] = mapped_column(String(32), index=True)
    job_title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))
    match_score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ImageRow(Base):
    """A generated image cached by name (e.g. persona portraits), shared by all users."""

    __tablename__ = "images"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    mime: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    data: Mapped[bytes] = mapped_column(LargeBinary)


def normalize_url(url: str) -> str:
    """Accept a plain Postgres URL (what Neon and most hosts hand out) and pin the psycopg driver.

    SQLAlchemy's bare `postgresql://` means psycopg2, which is not installed here.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str) -> Engine:
    """Engine for `url` with tables created; SQLite gets the settings Streamlit threads need."""
    url = normalize_url(url)
    if not url.startswith("sqlite"):
        # Hosted Postgres (Neon) is reached through its connection pooler in transaction mode;
        # psycopg's server-side prepared statements can break behind such poolers, so they are
        # off. pool_pre_ping re-opens connections the (auto-suspending) server dropped.
        engine = create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
        Base.metadata.create_all(engine)
        return engine
    # Streamlit runs each rerun on a different thread, so SQLite must allow cross-thread use.
    kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool  # one shared connection, or each thread sees an empty DB
    else:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return engine


@lru_cache(maxsize=4)
def get_engine(url: str) -> Engine:
    """Process-wide engine per URL (a connection pool is shared, not per browser session)."""
    return make_engine(url)
