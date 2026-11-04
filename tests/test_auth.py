"""Sign-in gate rules and production hardening (pure functions; Streamlit is not driven)."""

from __future__ import annotations

from interview_app.config import Settings
from interview_app.ui.auth import is_allowed


def test_allowlist_is_case_and_whitespace_insensitive() -> None:
    s = Settings(openrouter_api_key="t", allowed_emails=" Sonali@Example.com, other@x.io ")
    assert s.allowed_email_set == frozenset({"sonali@example.com", "other@x.io"})
    assert is_allowed("SONALI@example.com ", s.allowed_email_set)
    assert not is_allowed("stranger@example.com", s.allowed_email_set)


def test_empty_allowlist_admits_nobody() -> None:
    assert not is_allowed("anyone@example.com", frozenset())
    assert not is_allowed(None, frozenset({"anyone@example.com"}))
    assert not is_allowed("", frozenset({"anyone@example.com"}))


def test_prod_forces_the_guard_to_fail_closed() -> None:
    local = Settings(openrouter_api_key="t", app_env="local", guard_fail_closed=False)
    prod = Settings(openrouter_api_key="t", app_env="prod", guard_fail_closed=False)
    assert local.guard_fail_closed is False and not local.is_prod
    assert prod.guard_fail_closed is True and prod.is_prod
