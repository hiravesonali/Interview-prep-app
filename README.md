# Hoot · AI Interview Prep

AI interview coach for technical roles. Two features, one dashboard, every prompt routed
through a **security guard** to the **OpenRouter** API.

> Sprint 1 (Turing College AI Engineering). Architecture and delivery plan: [PLAN.md](PLAN.md).

## Features

| Feature | Status |
|---|---|
| Dashboard: hero, role cards with search, recent sessions, guard playground | ✅ day 1–2 |
| Security guard (rules + LLM classifier + output guard) with live log | ✅ day 1 |
| Cost / token meter per session | ✅ day 1 |
| Practice session: generated or JD-based questions, guided or mock mode, structured feedback, summary, retry weak ones, local history | ✅ day 2 |
| Job-description analyzer: skills, likely questions, prep plan → practice hand-off | ✅ day 2 |
| Prompt Lab: 5 system-prompt techniques compared on the same answer, rated, leaderboard | ✅ day 3 |

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
- `src/interview_app/features/` — `jd_analyzer.py`, `practice.py` (session state machine + LLM
  operations) and `prompt_lab.py` (parallel comparison of prompt variants).
- `src/interview_app/storage/history.py` — finished sessions saved as JSON in `data/sessions/`.
- `src/interview_app/ui/` — Streamlit pages and shared components. `theme.py` holds the brand (owl
  mascot as inline SVG), the colour tokens and the CSS that styles keyed containers
  (`st.container(key=...)` → `.st-key-...`); `.streamlit/config.toml` carries the native theme
  (Tailwind palette "violet-amber": zinc neutrals, violet→pink hero, amber-500 accent; Plus Jakarta Sans; 12px radius).
  Palettes are dictionaries in `theme.py` (`PALETTES`, `ACTIVE_PALETTE`); the sidebar brand is pinned with
  `position: sticky` on Streamlit's layout wrapper while the rest of the sidebar scrolls.

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

## Prompt engineering: five techniques, one task

The answer-feedback task has five system prompts in `src/interview_app/llm/prompts/feedback/`,
one per technique. The sidebar selects which one scores your answers; the **Prompt Lab** page runs
all five on the same question and answer in parallel, shows score, cost, latency and the full
feedback side by side, and stores your 1-5 usefulness rating in `data/prompt_lab.json`. The
leaderboard aggregates every saved run.

| # | Technique | How it is applied |
|---|---|---|
| 1 | Zero-shot | plain instruction, no examples |
| 2 | Few-shot | three worked examples (weak / solid / strong answer with feedback) calibrate the scoring |
| 3 | Chain-of-thought | an evidence-first `analysis` field (what was asked, what was said, what is missing) is filled before the scores |
| 4 | Role + rubric | interviewer persona plus 1/3/5 anchors per dimension |
| 5 | Self-critique | draft → checklist critique → revised feedback; the critique summary is returned in `analysis` |

Prompts 02-05 are first drafts; tuning them is part of the comparison work.

Two findings from building this:
- Anthropic's content filter refuses a prompt that asks the model to "reason explicitly and put your
  reasoning in the output": it reads as extracting chain-of-thought. Rephrasing the same technique as
  "write a structured analysis of the candidate's answer before scoring" passes and works well.
- Techniques differ more in cost than in verdict on the sample answer: self-critique costs ~1.6× zero-shot
  and takes ~1.7× longer; few-shot adds ~1 000 prompt tokens per call.

**Results**: _run the Lab, rate the variants, then record the winner here._
