"""The single choke point for LLM calls. Features never call the client directly."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TypeVar

from openai import PermissionDeniedError
from pydantic import BaseModel

from interview_app.config import Settings
from interview_app.guard.decision import GuardDecision, InputKind
from interview_app.guard.input_guard import InputGuard
from interview_app.guard.llm_guard import LLMGuard
from interview_app.guard.log import SecurityLog
from interview_app.guard.output_guard import OutputGuard
from interview_app.llm.client import (
    ChatResult,
    ImageResult,
    Message,
    OpenRouterClient,
    StructuredResult,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class CallOverrides:
    """Developer settings from the sidebar. `None` keeps each call's own default.

    `temperature` applies to every main-model call. `max_tokens` applies to text calls only
    (`chat`, `stream`): structured calls size their JSON budget per task, and a small cap
    would truncate them. The guard classifier is never affected.
    """

    temperature: float | None = None
    max_tokens: int | None = None

    def pick_temperature(self, default: float) -> float:
        return default if self.temperature is None else self.temperature

    def pick_max_tokens(self, default: int) -> int:
        return default if self.max_tokens is None else self.max_tokens


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
        cost_today: Callable[[], float] | None = None,
        cost_today_all_users: Callable[[], float] | None = None,
    ) -> None:
        """`cost_today` returns the user's spend so far today (USD) and `cost_today_all_users`
        everyone's; when given, calls are refused at `settings.max_daily_cost_usd` and
        `settings.max_daily_cost_total_usd` respectively. The app passes the `Store` methods."""
        self.client = client
        self.settings = settings
        self.log = log
        self.cost_today = cost_today
        self.cost_today_all_users = cost_today_all_users
        self.input_guard = InputGuard()
        self.output_guard = OutputGuard()
        self.llm_guard = LLMGuard(client, settings.guard_model, settings.guard_fail_closed)
        self.llm_guard_enabled = (
            settings.llm_guard_enabled if llm_guard_enabled is None else llm_guard_enabled
        )
        self.overrides = CallOverrides()

    # ----- input side -----

    def check_budget(self, kind: InputKind) -> None:
        """Daily spend caps, checked before any paid call (the classifier included).

        Two layers: a per-user cap bounds one person, a global cap bounds the worst day of a
        public deployment even if someone brings many accounts. Both are persisted, unlike the
        sidebar's per-session soft limit that resets on refresh.
        """
        caps = (
            (self.cost_today, self.settings.max_daily_cost_usd, "daily_budget", "Your daily"),
            (
                self.cost_today_all_users,
                self.settings.max_daily_cost_total_usd,
                "daily_budget_total",
                "The app's daily",
            ),
        )
        for read_spend, limit, category, label in caps:
            if read_spend is None:
                continue
            spent = read_spend()
            if spent < limit:
                continue
            decision = GuardDecision.block(
                "budget",
                category,
                f"{label} spend limit is reached (${spent:.2f} of ${limit:.2f} today). "
                "Try again tomorrow.",
            )
            self.log.record(decision, kind.value)
            raise GuardBlocked(decision)

    def check_input(self, text: str, kind: InputKind) -> GuardDecision:
        """Budget, then rules (free), then the classifier. Returns the decision to forward."""
        self.check_budget(kind)
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
        max_tokens: int = 2000,
        purpose: str = "chat",
    ) -> ChatResult:
        safe = self.check_input(user_text, kind)
        try:
            result = self.client.chat(
                self._build_messages(system_prompt, safe.text, history, user_template),
                model=model,
                temperature=self.overrides.pick_temperature(temperature),
                max_tokens=self.overrides.pick_max_tokens(max_tokens),
                purpose=purpose,
            )
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        text = self.check_output(result.text, system_prompt)
        return ChatResult(text=text, usage=result.usage, finish_reason=result.finish_reason)

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
                temperature=self.overrides.pick_temperature(temperature),
                max_tokens=max_tokens,
                purpose=purpose,
            )
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        # For JSON we only need the block decision (leak); a "sanitized" copy of the raw text
        # is not used because the validated pydantic object is what the UI renders.
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
        max_tokens: int = 2000,
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
                temperature=self.overrides.pick_temperature(temperature),
                max_tokens=self.overrides.pick_max_tokens(max_tokens),
                purpose=purpose,
            ):
                chunks.append(delta)
                yield delta
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err
        self.check_output("".join(chunks), system_prompt)

    def image(self, prompt: str, *, purpose: str = "image") -> ImageResult:
        """App-authored prompt → image. No user text, so only the budget guard and the cost
        ledger apply; a 403 from the allowlist becomes an `openrouter_guardrail` block."""
        self.check_budget(InputKind.FREE_TEXT)
        try:
            return self.client.generate_image(prompt, purpose=purpose)
        except PermissionDeniedError as err:
            raise GuardBlocked(self._openrouter_block(err)) from err

    @staticmethod
    def _openrouter_block(err: PermissionDeniedError) -> GuardDecision:
        return GuardDecision.block(
            "openrouter", "openrouter_guardrail", f"Blocked by OpenRouter guardrails: {err}"
        )
