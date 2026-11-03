"""The single choke point for LLM calls. Features never call the client directly."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

from openai import PermissionDeniedError
from pydantic import BaseModel

from interview_app.config import Settings
from interview_app.guard.decision import GuardDecision, InputKind
from interview_app.guard.input_guard import InputGuard
from interview_app.guard.llm_guard import LLMGuard
from interview_app.guard.log import SecurityLog
from interview_app.guard.output_guard import OutputGuard
from interview_app.llm.client import ChatResult, Message, OpenRouterClient, StructuredResult

T = TypeVar("T", bound=BaseModel)


class GuardBlocked(Exception):
    def __init__(self, decision: GuardDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class GuardPipeline:
    def __init__(
        self,
        client: OpenRouterClient,
        settings: Settings,
        log: SecurityLog,
        *,
        llm_guard_enabled: bool | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.log = log
        self.input_guard = InputGuard()
        self.output_guard = OutputGuard()
        self.llm_guard = LLMGuard(client, settings.guard_model, settings.guard_fail_closed)
        self.llm_guard_enabled = (
            settings.llm_guard_enabled if llm_guard_enabled is None else llm_guard_enabled
        )

    # ----- input side -----

    def check_input(self, text: str, kind: InputKind) -> GuardDecision:
        """Rules first (free), then the classifier. Returns the decision to forward."""
        decision = self.input_guard.check(text, kind)
        self.log.record(decision, kind.value)
        if not decision.allowed:
            raise GuardBlocked(decision)
        if self.llm_guard_enabled:
            llm_decision = self.llm_guard.check(decision.text, kind)
            self.log.record(llm_decision, kind.value)
            if not llm_decision.allowed:
                raise GuardBlocked(llm_decision)
        return decision

    # ----- output side -----

    def check_output(self, output: str, system_prompt: str) -> str:
        decision = self.output_guard.check(output, system_prompt)
        self.log.record(decision, "output")
        if not decision.allowed:
            raise GuardBlocked(decision)
        return decision.text

    # ----- guarded calls -----

    def _build_messages(
        self,
        system_prompt: str,
        user_text: str,
        history: list[Message] | None,
        user_template: str = "{input}",
    ) -> list[Message]:
        """`user_template` is app-authored context (e.g. the question) wrapped around the
        guard-checked user text; only `{input}` is replaced, so braces elsewhere are safe."""
        return [
            {"role": "system", "content": system_prompt},
            *(history or []),
            {"role": "user", "content": user_template.replace("{input}", user_text)},
        ]

    def chat(
        self,
        system_prompt: str,
        user_text: str,
        kind: InputKind,
        *,
        history: list[Message] | None = None,
        user_template: str = "{input}",
        model: str | None = None,
        temperature: float = 0.4,
        purpose: str = "chat",
    ) -> ChatResult:
        safe = self.check_input(user_text, kind)
        try:
            result = self.client.chat(
                self._build_messages(system_prompt, safe.text, history, user_template),
                model=model,
                temperature=temperature,
                purpose=purpose,
            )
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        text = self.check_output(result.text, system_prompt)
        return ChatResult(text=text, usage=result.usage)

    def structured(
        self,
        system_prompt: str,
        user_text: str,
        kind: InputKind,
        schema: type[T],
        *,
        history: list[Message] | None = None,
        user_template: str = "{input}",
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        purpose: str = "structured",
    ) -> StructuredResult[T]:
        safe = self.check_input(user_text, kind)
        try:
            result = self.client.chat_structured(
                self._build_messages(system_prompt, safe.text, history, user_template),
                schema,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                purpose=purpose,
            )
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        self.check_output(result.raw, system_prompt)
        return result

    def stream(
        self,
        system_prompt: str,
        user_text: str,
        kind: InputKind,
        *,
        history: list[Message] | None = None,
        user_template: str = "{input}",
        model: str | None = None,
        temperature: float = 0.5,
        purpose: str = "stream",
    ) -> Iterator[str]:
        """Yield deltas as they arrive; the output guard runs on the full text at the end.

        If the final check blocks, GuardBlocked is raised after streaming, so the caller
        must replace what it already displayed.
        """
        safe = self.check_input(user_text, kind)
        chunks: list[str] = []
        try:
            for delta in self.client.stream(
                self._build_messages(system_prompt, safe.text, history, user_template),
                model=model,
                temperature=temperature,
                purpose=purpose,
            ):
                chunks.append(delta)
                yield delta
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        self.check_output("".join(chunks), system_prompt)

    @staticmethod
    def _openrouter_block(err: PermissionDeniedError) -> GuardDecision:
        return GuardDecision.block(
            "openrouter", "openrouter_guardrail", f"Blocked by OpenRouter guardrails: {err}"
        )
