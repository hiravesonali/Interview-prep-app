"""Thin OpenRouter client built on the official `openai` SDK.

OpenRouter speaks the OpenAI chat-completions protocol, so we only change `base_url`.
Three call styles are exposed:
  - chat()            plain text answer
  - chat_structured() JSON constrained to a pydantic schema, validated and retried once
  - stream()          token stream for the coaching UI

Every call records a `Usage` (tokens, USD cost, latency) in a `UsageTracker`.
Cost comes straight from OpenRouter (`usage.cost`) when we pass `usage: {include: true}`,
so no local price table is needed.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from interview_app.config import Settings

T = TypeVar("T", bound=BaseModel)

Message = dict[str, str]


@dataclass(frozen=True)
class Usage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_s: float
    purpose: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class UsageTracker:
    calls: list[Usage] = field(default_factory=list)

    def add(self, usage: Usage) -> None:
        self.calls.append(usage)

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(u.total_tokens for u in self.calls)


@dataclass(frozen=True)
class ChatResult:
    text: str
    usage: Usage


@dataclass(frozen=True)
class StructuredResult[T]:
    data: T
    raw: str
    usage: Usage


class StructuredOutputError(RuntimeError):
    """The model did not return JSON matching the schema, even after a repair retry."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _ascii(value: str) -> str:
    return value.encode("ascii", "ignore").decode("ascii").strip()


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def _usage_from_response(resp: Any, model: str, latency_s: float, purpose: str) -> Usage:
    u = getattr(resp, "usage", None)
    cost = 0.0
    if u is not None:
        # `cost` is an OpenRouter extension; the SDK keeps unknown fields in model_extra.
        cost = getattr(u, "cost", None) or (u.model_extra or {}).get("cost") or 0.0
    return Usage(
        model=model,
        prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(u, "completion_tokens", 0) or 0,
        cost_usd=float(cost),
        latency_s=latency_s,
        purpose=purpose,
    )


class OpenRouterClient:
    def __init__(self, settings: Settings, tracker: UsageTracker | None = None) -> None:
        self.settings = settings
        self.tracker = tracker or UsageTracker()
        self._client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key.get_secret_value() or "missing",
            default_headers={
                # Optional OpenRouter attribution headers (show up in their dashboard).
                # HTTP headers must be ASCII: a stray en dash here breaks every request.
                "HTTP-Referer": _ascii(settings.app_url),
                "X-Title": _ascii(settings.app_title),
            },
            timeout=90,
            max_retries=2,
        )

    # ----- plain chat -----

    def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2000,
        purpose: str = "chat",
    ) -> ChatResult:
        model = model or self.settings.default_model
        t0 = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"usage": {"include": True}},
        )
        usage = _usage_from_response(resp, model, time.perf_counter() - t0, purpose)
        self.tracker.add(usage)
        text = resp.choices[0].message.content or ""
        return ChatResult(text=text, usage=usage)

    # ----- structured output -----

    def chat_structured(
        self,
        messages: list[Message],
        schema: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        purpose: str = "structured",
    ) -> StructuredResult[T]:
        """Ask for JSON matching `schema`; validate; on failure retry once with the error."""
        model = model or self.settings.default_model
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
        attempt_messages = list(messages)
        last_error: Exception | None = None
        for attempt in range(2):
            t0 = time.perf_counter()
            resp = self._client.chat.completions.create(
                model=model,
                messages=attempt_messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,  # type: ignore[arg-type]
                extra_body={"usage": {"include": True}},
            )
            usage = _usage_from_response(
                resp, model, time.perf_counter() - t0, f"{purpose}:try{attempt + 1}"
            )
            self.tracker.add(usage)
            choice = resp.choices[0]
            raw = _strip_fences(choice.message.content or "")
            if choice.finish_reason == "length":
                # A repair turn cannot fix a cut-off response; fail fast instead.
                raise StructuredOutputError(
                    f"Response truncated at max_tokens={max_tokens}; raise the limit."
                )
            if choice.finish_reason == "content_filter":
                # Provider-side refusal (e.g. Anthropic's filter); retrying won't help.
                refusal = getattr(choice.message, "refusal", None) or "no details"
                raise StructuredOutputError(f"Refused by the provider's content filter: {refusal}")
            try:
                data = schema.model_validate_json(raw)
                return StructuredResult(data=data, raw=raw, usage=usage)
            except (ValidationError, json.JSONDecodeError) as err:
                last_error = err
                # Repair turn: show the model its own output and the validation error.
                attempt_messages = [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            "Your previous output did not match the required JSON schema. "
                            f"Error: {err}\nReturn ONLY corrected JSON, no prose."
                        ),
                    },
                ]
        raise StructuredOutputError(str(last_error))

    # ----- streaming -----

    def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.5,
        max_tokens: int = 2000,
        purpose: str = "stream",
    ) -> Iterator[str]:
        """Yield text deltas. Usage is recorded after the final chunk arrives."""
        model = model or self.settings.default_model
        t0 = time.perf_counter()
        stream = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={"usage": {"include": True}},
        )
        last_chunk = None
        for chunk in stream:
            last_chunk = chunk
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        self.tracker.add(_usage_from_response(last_chunk, model, time.perf_counter() - t0, purpose))
