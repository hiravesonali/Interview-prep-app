"""Client tests with a fake OpenAI transport (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from interview_app.config import Settings
from interview_app.llm.client import OpenRouterClient, StructuredOutputError


class Verdict(BaseModel):
    ok: bool
    note: str


def _response(content: str, cost: float = 0.001, finish_reason: str = "stop", refusal=None):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=cost, model_extra={})
    message = SimpleNamespace(content=content, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.fixture
def client(monkeypatch):
    c = OpenRouterClient(Settings(openrouter_api_key="test"))
    return c


def _install(monkeypatch, client, responses: list[str]):
    calls: list[dict] = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return _response(responses.pop(0))

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    return calls


def test_chat_records_usage(monkeypatch, client):
    _install(monkeypatch, client, ["hello"])
    r = client.chat([{"role": "user", "content": "hi"}], purpose="t")
    assert r.text == "hello"
    assert client.tracker.total_cost_usd == pytest.approx(0.001)
    assert client.tracker.total_tokens == 15


def test_structured_parses_and_strips_fences(monkeypatch, client):
    _install(monkeypatch, client, ['```json\n{"ok": true, "note": "x"}\n```'])
    r = client.chat_structured([{"role": "user", "content": "q"}], Verdict)
    assert r.data == Verdict(ok=True, note="x")


def test_structured_repairs_once(monkeypatch, client):
    calls = _install(monkeypatch, client, ['{"ok": "maybe"}', '{"ok": false, "note": "fixed"}'])
    r = client.chat_structured([{"role": "user", "content": "q"}], Verdict)
    assert r.data.note == "fixed"
    assert len(calls) == 2
    assert "did not match" in calls[1]["messages"][-1]["content"]


def test_structured_gives_up_after_retry(monkeypatch, client):
    _install(monkeypatch, client, ["nope", "still nope"])
    with pytest.raises(StructuredOutputError):
        client.chat_structured([{"role": "user", "content": "q"}], Verdict)


def test_structured_truncation_fails_fast(monkeypatch, client):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return _response('{"ok": true, "no', finish_reason="length")

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    with pytest.raises(StructuredOutputError, match="truncated"):
        client.chat_structured([{"role": "user", "content": "q"}], Verdict, max_tokens=50)
    assert len(calls) == 1


def test_headers_are_ascii_even_with_fancy_title():
    c = OpenRouterClient(Settings(openrouter_api_key="t", app_title="Hoot \u2013 AI Prep"))
    title = c._client.default_headers["X-Title"]
    title.encode("ascii")  # must not raise
    assert title == "Hoot  AI Prep"


def test_structured_content_filter_fails_fast(monkeypatch, client):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return _response("", finish_reason="content_filter", refusal="blocked by policy")

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    with pytest.raises(StructuredOutputError, match="content filter.*blocked by policy"):
        client.chat_structured([{"role": "user", "content": "q"}], Verdict)
    assert len(calls) == 1
