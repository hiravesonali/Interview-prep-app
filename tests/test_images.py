"""Image generation: response parsing, pipeline budget, cache in the store, persona avatars."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from interview_app.config import Settings
from interview_app.features.avatars import PERSONA_PROMPTS, generate_avatar, get_avatar
from interview_app.guard import GuardBlocked, GuardPipeline, SecurityLog
from interview_app.llm.client import ImageGenerationError, ImageResult, OpenRouterClient, Usage
from interview_app.storage.db import make_engine
from interview_app.storage.store import Store

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _response(images: list | None, content: str = "") -> SimpleNamespace:
    message = SimpleNamespace(content=content, model_extra={"images": images} if images else {})
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=1290, cost=0.03, model_extra={})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeImageClient(OpenRouterClient):
    """Fakes the openai SDK call; `generate_image` itself runs for real (parsing is the point)."""

    def __init__(self, response):
        super().__init__(Settings(openrouter_api_key="t"))
        self.sent: list[dict] = []
        self._client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: self.sent.append(kw) or response)
            )
        )


def test_generate_image_parses_the_data_uri_and_records_usage() -> None:
    uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    client = FakeImageClient(_response([{"type": "image_url", "image_url": {"url": uri}}]))
    result = client.generate_image("a portrait", purpose="avatar:test")
    assert result.data == PNG and result.mime == "image/png"
    assert result.usage.cost_usd == 0.03 and result.usage.purpose == "avatar:test"
    sent = client.sent[0]
    assert sent["model"] == "google/gemini-3.1-flash-image"
    assert sent["extra_body"]["modalities"] == ["image", "text"]


def test_text_only_reply_is_an_error() -> None:
    client = FakeImageClient(_response(None, content="I cannot draw that."))
    with pytest.raises(ImageGenerationError, match="cannot draw"):
        client.generate_image("x")


def test_pipeline_image_respects_the_daily_budget() -> None:
    client = FakeImageClient(_response(None))
    settings = Settings(openrouter_api_key="t", max_daily_cost_usd=1.0)
    pipe = GuardPipeline(
        client, settings, SecurityLog(), cost_today=lambda: 1.0, llm_guard_enabled=False
    )
    with pytest.raises(GuardBlocked) as exc:
        pipe.image("x")
    assert exc.value.decision.layer == "budget"
    assert client.sent == []


def test_store_image_cache_round_trip() -> None:
    store = Store(make_engine("sqlite://"), "alice")
    assert store.load_image("avatar_strict") is None
    store.save_image("avatar_strict", PNG, "image/png", "m")
    assert store.load_image("avatar_strict") == (PNG, "image/png")
    assert Store(store.engine, "bob").load_image("avatar_strict") == (PNG, "image/png")  # shared


def test_generate_avatar_caches_for_everyone() -> None:
    class Pipe:
        def __init__(self):
            self.prompts: list[str] = []

        def image(self, prompt, *, purpose=""):
            self.prompts.append(prompt)
            return ImageResult(PNG, "image/png", Usage("img", 1, 1, 0.03, 2.0, purpose))

    store = Store(make_engine("sqlite://"), "alice")
    pipe = Pipe()
    generate_avatar(pipe, store, "friendly")  # type: ignore[arg-type]
    assert pipe.prompts == [PERSONA_PROMPTS["friendly"]]
    assert get_avatar(Store(store.engine, "bob"), "friendly") == (PNG, "image/png")
