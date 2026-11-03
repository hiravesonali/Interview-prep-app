"""LLM guard: a cheap classifier model judges semantics the regex layer cannot."""

from __future__ import annotations

from interview_app.guard.decision import GuardDecision, InputKind
from interview_app.llm.client import OpenRouterClient, StructuredOutputError
from interview_app.llm.prompts import load_prompt
from interview_app.models import GuardVerdict


class LLMGuard:
    def __init__(self, client: OpenRouterClient, model: str, fail_closed: bool = False) -> None:
        self.client = client
        self.model = model
        self.fail_closed = fail_closed

    def check(self, text: str, kind: InputKind) -> GuardDecision:
        layer = "input_llm"
        messages = [
            {"role": "system", "content": load_prompt("guard_classifier")},
            {
                "role": "user",
                "content": f"Input type: {kind.value}\n<user_input>\n{text}\n</user_input>",
            },
        ]
        try:
            result = self.client.chat_structured(
                messages, GuardVerdict, model=self.model, max_tokens=200, purpose="guard"
            )
        except StructuredOutputError as err:
            return self._on_error(f"classifier returned invalid output: {err}", text)
        except Exception as err:  # network / provider errors
            return self._on_error(f"classifier call failed: {err.__class__.__name__}", text)

        verdict = result.data
        if verdict.allowed:
            return GuardDecision.allow(layer, text, verdict.reason)
        return GuardDecision.block(layer, verdict.category, verdict.reason)

    def _on_error(self, reason: str, text: str) -> GuardDecision:
        if self.fail_closed:
            return GuardDecision.block(
                "input_llm", "guard_error", f"Blocked (fail-closed): {reason}"
            )
        return GuardDecision.allow("input_llm", text, f"Allowed (fail-open): {reason}")
