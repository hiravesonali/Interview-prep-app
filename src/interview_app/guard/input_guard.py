"""Deterministic input guard: no network, microseconds, fully unit-tested.

Order of checks (first hit wins):
  1. empty / too long            -> block
  2. secrets (API keys, private keys) -> block  (never send credentials to a model)
  3. prompt-injection patterns   -> block  (OWASP LLM prompt-injection cheat-sheet style)
  4. encoded payloads (base64 blobs) -> block
  5. PII (emails, phone numbers) -> redact and allow

Pattern matching runs on a normalized copy (NFKC, zero-width chars removed) and on a
"compact" copy with all whitespace removed, which defeats the `i g n o r e` spacing trick.
"""

from __future__ import annotations

import re
import unicodedata

from interview_app.guard.decision import GuardDecision, InputKind

MAX_CHARS: dict[InputKind, int] = {
    InputKind.ANSWER: 6000,
    InputKind.JOB_DESCRIPTION: 12000,
    InputKind.TITLE: 120,
    InputKind.FREE_TEXT: 4000,
}

_ZERO_WIDTH = re.compile(r"[​-‏⁠﻿]")

# Each entry: (label, regex). Written with `\s+` between words; a compact variant with
# `\s*` is derived automatically for the whitespace-stripped text.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (
        "ignore_instructions",
        r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+|your\s+|of\s+)*"
        r"(previous|prior|above|earlier|preceding|initial|system|these)\s+"
        r"(instructions?|prompts?|rules|directions|guidelines|context)",
    ),
    (
        "reveal_system_prompt",
        r"(reveal|print|show|output|repeat|display|leak|dump|tell\s+me)\s+(me\s+)?"
        r"(your|the|its)\s+(system|initial|hidden|secret|original)\s+"
        r"(prompt|instructions?|message|rules)",
    ),
    ("ask_system_prompt", r"what\s+(is|are|were)\s+your\s+(system\s+prompt|instructions|rules)"),
    ("role_override", r"you\s+are\s+now\s+(a|an|in|the|my)\b"),
    ("from_now_on", r"from\s+now\s+on\s*,?\s+(you|act|respond|answer|ignore|only)"),
    ("pretend", r"pretend\s+(that\s+)?(you\s+are|to\s+be|you're)"),
    (
        "override_rules",
        r"override\s+(all\s+|the\s+|your\s+)*(rules|instructions|guidelines|safety|restrictions)",
    ),
    (
        "bypass_safety",
        r"(bypass|disable|turn\s+off|remove)\s+(all\s+|the\s+|your\s+)*"
        r"(safety|filters?|guardrails?|restrictions|content\s+policy|moderation)",
    ),
    ("jailbreak", r"\b(jailbreak|jailbroken)\b"),
    ("dan", r"do\s+anything\s+now"),
    ("dev_mode", r"(developer|god|unrestricted)\s+mode"),
    ("new_instructions", r"new\s+(system\s+)?instructions?\s*:"),
    ("fake_role_line", r"(^|\n)\s*(system|assistant)\s*:"),
    (
        "chat_template_tokens",
        r"<\|im_(start|end)\|>|\[/?INST\]|<<SYS>>|<\|(system|user|assistant)\|>",
    ),
    ("markdown_system_header", r"###\s*(system|instructions?)\b|\bBEGIN\s+SYSTEM\b"),
]

_SECRET_PATTERNS: list[tuple[str, str]] = [
    ("openrouter_key", r"sk-or-v1-[A-Za-z0-9]{20,}"),
    ("openai_style_key", r"\bsk-[A-Za-z0-9_\-]{20,}"),
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    ("private_key", r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    (
        "key_assignment",
        r"(api[_\- ]?key|secret[_\- ]?key|access[_\- ]?token|password)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
    ),
]

_BASE64_BLOB = re.compile(r"(?:[A-Za-z0-9+/]{4}){40,}={0,2}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_CANDIDATE = re.compile(r"(?<![\w/])\+?\d[\d\s().\-]{7,}\d(?![\w/])")


def _compile(patterns: list[tuple[str, str]]) -> list[tuple[str, re.Pattern[str], re.Pattern[str]]]:
    out = []
    for label, pat in patterns:
        normal = re.compile(pat, re.IGNORECASE)
        compact = re.compile(pat.replace(r"\s+", r"\s*"), re.IGNORECASE)
        out.append((label, normal, compact))
    return out


_INJECTION = _compile(_INJECTION_PATTERNS)
_SECRETS = _compile(_SECRET_PATTERNS)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return text


def _find(
    compiled: list[tuple[str, re.Pattern[str], re.Pattern[str]]], text: str
) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", text)
    hits: list[str] = []
    for label, normal, compact_re in compiled:
        if normal.search(text) or compact_re.search(compact):
            hits.append(label)
    return tuple(hits)


def _redact_pii(text: str) -> tuple[str, tuple[str, ...]]:
    found: list[str] = []
    if _EMAIL.search(text):
        found.append("email")
        text = _EMAIL.sub("[email]", text)

    def _phone(m: re.Match[str]) -> str:
        raw = m.group(0)
        groups = re.findall(r"\d+", raw)
        digits = sum(len(g) for g in groups)
        # Phone-like: international/trunk prefix or 3+ digit groups. This keeps salary
        # ranges ("70000-85000") and year ranges ("2019 - 2024") untouched.
        looks_like_phone = raw.startswith(("+", "(", "0")) or len(groups) >= 3
        if 9 <= digits <= 15 and looks_like_phone:
            found.append("phone")
            return "[phone]"
        return raw

    text = _PHONE_CANDIDATE.sub(_phone, text)
    return text, tuple(dict.fromkeys(found))


class InputGuard:
    def check(self, text: str, kind: InputKind = InputKind.FREE_TEXT) -> GuardDecision:
        layer = "input_rules"
        text = normalize(text).strip()
        if not text:
            return GuardDecision.block(layer, "empty", "Input is empty.")
        limit = MAX_CHARS[kind]
        if len(text) > limit:
            return GuardDecision.block(
                layer, "too_long", f"Input has {len(text)} characters; the limit is {limit}."
            )

        if secrets := _find(_SECRETS, text):
            return GuardDecision.block(
                layer, "secret", "Input looks like it contains credentials. Remove them.", secrets
            )
        if hits := _find(_INJECTION, text):
            return GuardDecision.block(
                layer, "prompt_injection", "Input matches prompt-injection patterns.", hits
            )
        if _BASE64_BLOB.search(text):
            return GuardDecision.block(
                layer, "encoded_payload", "Input contains a long encoded blob.", ("base64",)
            )

        if kind is not InputKind.TITLE:
            redacted, pii = _redact_pii(text)
            if pii:
                return GuardDecision.redact(
                    layer, "pii", f"Redacted {', '.join(pii)} before sending.", redacted, pii
                )
        return GuardDecision.allow(layer, text)
