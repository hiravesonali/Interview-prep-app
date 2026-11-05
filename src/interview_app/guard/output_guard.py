"""Output guard: checks what comes back from the model before it reaches the UI.

- system-prompt leakage: any long line of the system prompt echoed verbatim -> block
- secrets in the output (model repeating a key it was shown) -> redact
- active HTML (<script>, <iframe>, event handlers) -> stripped; Streamlit renders
  markdown, so this is defence in depth rather than the main XSS barrier
"""

from __future__ import annotations

import re

from interview_app.guard.decision import GuardDecision
from interview_app.guard.input_guard import _SECRETS, _find

_MIN_LEAK_LINE = 60
_SCRIPT_RE = re.compile(r"<\s*(script|iframe|object|embed)\b.*?>.*?<\s*/\s*\1\s*>", re.I | re.S)
_ON_HANDLER_RE = re.compile(r"\son\w+\s*=\s*(['\"]).*?\1", re.I | re.S)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class OutputGuard:
    def check(self, output: str, system_prompt: str = "") -> GuardDecision:
        layer = "output"
        squashed_out = _squash(output)
        leaked = [
            i
            for i, line in enumerate(system_prompt.splitlines(), 1)
            if len(line.strip()) >= _MIN_LEAK_LINE and _squash(line) in squashed_out
        ]
        if leaked:
            # Only line numbers go to the log and the security_events table: the log is shown
            # in the sidebar, so quoting the prompt there would be a leak of its own.
            return GuardDecision.block(
                layer,
                "leak",
                "Response echoed the system prompt and was withheld.",
                tuple(f"system prompt line {i}" for i in leaked),
            )

        cleaned = _SCRIPT_RE.sub("", output)
        cleaned = _ON_HANDLER_RE.sub("", cleaned)
        matches: list[str] = []
        if cleaned != output:
            matches.append("html")
        if secrets := _find(_SECRETS, cleaned):
            matches.extend(secrets)
            for _, normal, _ in _SECRETS:
                cleaned = normal.sub("[redacted]", cleaned)
        if matches:
            return GuardDecision.redact(
                layer, "sanitized", "Response was sanitized.", cleaned, tuple(matches)
            )
        return GuardDecision.allow(layer, output)
