"""Audit trail and spend ledger: the two sinks and the daily cost query."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from interview_app.guard.decision import GuardDecision
from interview_app.guard.log import SecurityLog
from interview_app.llm.client import Usage, UsageTracker
from interview_app.storage.db import SecurityEventRow, make_engine
from interview_app.storage.store import Store


def test_security_events_are_persisted_per_user() -> None:
    engine = make_engine("sqlite://")
    log = SecurityLog(sink=Store(engine, "alice").record_security_event)
    log.record(GuardDecision.block("input_rules", "prompt_injection", "bad", ("ignore",)), "answer")
    log.record(GuardDecision.allow("output", "ok"), "output")
    with Session(engine) as db:
        rows = db.scalars(select(SecurityEventRow).order_by(SecurityEventRow.id)).all()
    assert [(r.user_id, r.layer, r.action, r.matches) for r in rows] == [
        ("alice", "input_rules", "block", ["ignore"]),
        ("alice", "output", "allow", []),
    ]


def test_cost_today_sums_only_today_and_only_this_user() -> None:
    engine = make_engine("sqlite://")
    alice, bob = Store(engine, "alice"), Store(engine, "bob")
    tracker = UsageTracker(sink=alice.record_usage)
    tracker.add(Usage("m", 10, 5, 0.30, 1.0, "chat"))
    tracker.add(Usage("guard", 10, 5, 0.01, 0.2, "guard"))  # guard calls count too
    alice.record_usage(Usage("m", 1, 1, 9.0, 1.0), at=datetime.now() - timedelta(days=1))
    bob.record_usage(Usage("m", 1, 1, 9.0, 1.0))
    assert round(alice.cost_today(), 2) == 0.31
    assert bob.cost_today() == 9.0
    assert Store(engine, "nobody").cost_today() == 0.0
