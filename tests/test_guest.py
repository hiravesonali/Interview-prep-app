"""Guest demo: isolated ids, a shared daily cap for all guests, and the 24 h purge."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from interview_app.config import Settings
from interview_app.guard import GuardPipeline, InputKind, SecurityLog
from interview_app.guard.pipeline import GuardBlocked
from interview_app.llm.client import Usage
from interview_app.storage.db import UsageEventRow, make_engine
from interview_app.storage.store import GUEST_PREFIX, Store, is_guest_id
from interview_app.ui.auth import new_guest_id
from tests.test_pipeline import FakeClient
from tests.test_practice import _session
from tests.test_resume import _base


def test_guest_ids_are_prefixed_and_unique() -> None:
    a, b = new_guest_id(), new_guest_id()
    assert a != b
    assert is_guest_id(a) and a.startswith(GUEST_PREFIX)
    assert not is_guest_id("local") and not is_guest_id("someone@example.com")


def test_guest_mode_is_off_unless_enabled() -> None:
    assert Settings(_env_file=None).guest_mode_enabled is False


def test_guests_do_not_see_each_others_data() -> None:
    engine = make_engine("sqlite://")
    one, two = Store(engine, new_guest_id()), Store(engine, new_guest_id())
    one.save_session(_session())
    one.save_resume(_base())
    assert two.list_sessions() == [] and two.list_resumes() == []
    assert len(one.list_sessions()) == 1 and len(one.list_resumes()) == 1


def test_cost_today_guests_sums_every_guest_but_no_signed_in_user() -> None:
    engine = make_engine("sqlite://")
    Store(engine, new_guest_id()).record_usage(Usage("m", 1, 1, 0.5, 1.0))
    Store(engine, new_guest_id()).record_usage(Usage("m", 1, 1, 0.25, 1.0))
    Store(engine, "alice@example.com").record_usage(Usage("m", 1, 1, 9.0, 1.0))
    yesterday = datetime.now() - timedelta(days=1)
    Store(engine, new_guest_id()).record_usage(Usage("m", 1, 1, 5.0, 1.0), at=yesterday)
    assert Store(engine, "anyone").cost_today_guests() == 0.75


def test_guest_budget_blocks_a_fresh_guest_once_all_guests_spent_the_cap() -> None:
    client = FakeClient("fine")
    client.settings.max_daily_cost_guest_usd = 3.0
    pipe = GuardPipeline(
        client,
        client.settings,
        SecurityLog(),
        llm_guard_enabled=False,
        cost_today=lambda: 0.0,  # a new guest id has spent nothing itself
        cost_today_guests=lambda: 3.0,
    )
    with pytest.raises(GuardBlocked) as exc:
        pipe.chat("sys", "hello", InputKind.ANSWER)
    assert exc.value.decision.category == "daily_budget_guest"
    assert client.sent == []


def test_purge_removes_only_old_guest_data() -> None:
    engine = make_engine("sqlite://")
    old_guest, new_guest = Store(engine, new_guest_id()), Store(engine, new_guest_id())
    member = Store(engine, "alice@example.com")
    long_ago = datetime.now() - timedelta(hours=30)

    old_session = _session()
    old_session.started_at = long_ago
    old_guest.save_session(old_session)
    old_resume = _base().model_copy(update={"created_at": long_ago})
    old_guest.save_resume(old_resume)
    old_guest.record_usage(Usage("m", 1, 1, 0.1, 1.0), at=long_ago)

    new_guest.save_session(_session())
    member_session = _session()
    member_session.started_at = long_ago
    member.save_session(member_session)

    assert new_guest.purge_guest_data(timedelta(hours=24)) == 2
    assert old_guest.list_sessions() == [] and old_guest.list_resumes() == []
    assert len(new_guest.list_sessions()) == 1  # still within 24 h
    assert len(member.list_sessions()) == 1  # signed-in users are never purged
    # the spend ledger stays: the caps and the audit trail depend on it
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UsageEventRow)) == 1
