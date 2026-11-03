# Interview Practice App

AI interview coach for technical roles. Two features, one dashboard, every prompt routed
through a **security guard** to the **OpenRouter** API.

> Sprint 1 (Turing College AI Engineering). Architecture and delivery plan: [PLAN.md](PLAN.md).

## Features

| Feature | Status |
|---|---|
| Dashboard with role presets + custom job title | ✅ day 1 |
| Security guard (rules + LLM classifier + output guard) with live log | ✅ day 1 |
| Cost / token meter per session | ✅ day 1 |
| Practice session: generated or JD-based questions, guided or mock mode, structured feedback, summary, retry weak ones, local history | ✅ day 2 |
| Job-description analyzer: skills, likely questions, prep plan → practice hand-off | ✅ day 2 |
| Prompt Lab: 5 system-prompt techniques compared on the same answer | day 4 |

## Quick start

```bash
uv sync                        # installs Python 3.12 env + deps
cp .env.example .env           # add your OPENROUTER_API_KEY
uv run streamlit run app.py
```

Tests and lint:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Architecture

```
Streamlit pages ──► features ──► GuardPipeline ──► OpenRouter (openai SDK, base_url swapped)
                                   │  InputGuard   rules: length, secrets, injection, base64, PII
                                   │  LLMGuard     Haiku 5.5 classifier (structured verdict)
                                   │  OutputGuard  system-prompt leak, secrets, active HTML
                                   └─ SecurityLog  shown in the sidebar
```

- `src/interview_app/guard/` — the guard. `pipeline.py` is the only place that calls the LLM client.
- `src/interview_app/llm/client.py` — OpenRouter wrapper: `chat`, `chat_structured` (pydantic
  schema + one repair retry), `stream`. Cost comes from OpenRouter's `usage.cost`.
- `src/interview_app/llm/prompts/` — system prompts as Markdown files, loaded by name.
- `src/interview_app/models.py` — pydantic schemas for every structured call.
- `src/interview_app/features/` — `jd_analyzer.py` and `practice.py` (session state machine + LLM operations).
- `src/interview_app/storage/history.py` — finished sessions saved as JSON in `data/sessions/`.
- `src/interview_app/ui/` — Streamlit pages and shared components.

### Models (via OpenRouter)

| Purpose | Model | Why |
|---|---|---|
| Coaching, feedback, JD analysis | `anthropic/claude-sonnet-5.5` | capability |
| Guard classifier | `anthropic/claude-haiku-4.5` | runs on every request; cheaper and fast. Haiku 5.5 would be cheaper still but is blocked by the workspace model allowlist on the course API key |

Both are configurable in `.env`; the main model can be switched in the sidebar.

### Security design

1. **Rule-based input guard** (no network): blocks empty/over-long input, credentials
   (OpenRouter/OpenAI/AWS/GitHub keys, private keys), prompt-injection patterns
   (instruction override, system-prompt extraction, role override, chat-template tokens),
   and long base64 blobs. Emails and phone numbers are **redacted**, not blocked, because job
   descriptions legitimately contain them. Patterns are matched on NFKC-normalized text with
   zero-width characters removed and on a whitespace-stripped copy, so `i g n o r e` and
   `ig​nore` tricks are caught.
2. **LLM guard**: a cheap classifier returns `{allowed, category, reason}` for semantic
   attacks the regexes miss. Fail-open with a logged warning by default
   (`GUARD_FAIL_CLOSED=true` to flip).
3. **Output guard**: blocks responses that echo a line of the system prompt, strips active
   HTML, redacts secrets.
4. **OpenRouter native guardrails** (optional, zero code): enable prompt-injection blocking
   and a spend budget on the API key in the OpenRouter dashboard. A `403` from OpenRouter is
   surfaced in the security log as `openrouter_guardrail`.

Every decision is recorded in the sidebar **Security log**. Try the **Guard playground** on
the dashboard.
