# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

**Hoot** is a personal AI interview coach for technical roles (Full-stack, Frontend, Backend,
AI Engineer, Product Engineer, …). It is Sonali Hirave's Sprint 1 project for the Turing College
AI Engineering course and will be defended in a review, so design decisions must be explainable
and owned by her. `PLAN.md` is the approved architecture and delivery plan and is the source of
truth for decisions; `README.md` is the user-facing description (features, security design,
prompt-technique findings).

Three features, one dashboard, every LLM call routed through a security guard to OpenRouter:

- **Practice session**: generate ~10 questions for a role (or take them from a JD analysis), ask
  one at a time in guided mode (streamed coaching + hints) or mock mode, score each answer on
  four dimensions with structured feedback, end with a summary and a retry set. Sessions are
  saved as JSON in `data/sessions/`.
- **JD analyzer**: paste a job description → skills, likely questions, day-by-day prep plan,
  then a hand-off button that pre-loads a practice session with the JD's questions.
- **Prompt Lab**: the course requirement "5 system prompts with different techniques, compare
  them". Five feedback prompts (zero-shot, few-shot, chain-of-thought, role+rubric,
  self-critique) run in parallel on the same answer; ratings go to `data/prompt_lab.json` and
  feed a leaderboard. The README has a **Results** placeholder for the winner.

## Working agreement

- **Plan first, then code.** For new features or architecture changes, present the plan and
  wait for an explicit OK before writing code. Record decisions in `PLAN.md`.
- **Prompts are hers.** The feedback prompt variants 02–05 under `llm/prompts/feedback/` are
  drafts that Sonali tunes herself; do not rewrite them unasked.
- Commit and push only when asked. `.env` is gitignored; only `.env.example` is tracked.
- Deferred to after Sprint 1 (do not build unasked): RAG knowledge base (embeddings
  `qwen/qwen3-embedding-8b` default via OpenRouter), LangChain, deployment.
- Sonali is a senior JS/TS developer new to Python: point out JavaScript-style thinking and
  show the idiomatic Python version.

## Commands

```bash
uv sync                                   # Python 3.12 env + deps (uv-managed, src layout)
cp .env.example .env                      # then add OPENROUTER_API_KEY
uv run streamlit run app.py               # http://localhost:8501; auto-reruns on file save
uv run pytest                             # all tests are offline (fake clients), no API key needed
uv run pytest tests/test_input_guard.py   # one file
uv run pytest -k "redact"                 # by name
uv run ruff check . && uv run ruff format --check .
uv run ruff format .                      # fix formatting
```

Ruff: line length 100, rules E/F/I/UP/B/SIM; `ui/theme.py` is exempt from E501 (CSS/SVG strings).

## Architecture

```
app.py (st.navigation, hidden) → ui/pages/* → features/* → guard.GuardPipeline → llm.OpenRouterClient → OpenRouter
                                                               │ InputGuard   rules, no network
                                                               │ LLMGuard     Haiku classifier (fail-open by default)
                                                               │ OutputGuard  system-prompt leak, HTML, secrets
                                                               └ SecurityLog  shown in the sidebar
```

**The guard pipeline is the single choke point.** `guard/pipeline.py` is the only module that
calls `OpenRouterClient`; features call `pipe.chat`, `pipe.structured` or `pipe.stream` and never
the client. Each call takes the user text plus an `InputKind` (sets the length cap), and an
optional `user_template` where only `{input}` is replaced with the guard-checked text, so
app-authored context (the question, role, etc.) never passes through the guard and braces in it
are safe. A block raises `GuardBlocked(decision)`; pages render it with
`components.show_guard_block`. `stream` runs the output guard only after the full text, so a
caller must be ready to replace what it already displayed. A `PermissionDeniedError` (403) from
OpenRouter is converted into an `openrouter_guardrail` block.

**LLM client** (`llm/client.py`): the `openai` SDK with `base_url` swapped to OpenRouter.
Cost comes from OpenRouter's `usage.cost` (requested with `extra_body={"usage": {"include": True}}`)
and is accumulated in a per-session `UsageTracker`. `chat_structured` sends a pydantic JSON schema
via `response_format`, validates with `model_validate_json`, and does exactly one repair retry;
it raises `StructuredOutputError` immediately on `finish_reason` `length` (raise `max_tokens`
instead) or `content_filter`. HTTP headers (`X-Title`, `HTTP-Referer`) are forced to ASCII: a
non-ASCII app title once broke every request and silently made the LLM guard fail open.

**Prompts** are Markdown files in `llm/prompts/`, loaded by name without extension
(`load_prompt("feedback/01_zero_shot")`, `render_prompt(name, **vars)` substitutes `{{var}}`;
JSON braces stay untouched). `list_prompts("feedback")` is how the Prompt Lab discovers variants,
so adding a file there adds a technique. Every structured call has its pydantic schema in
`models.py`.

**Models**: main `anthropic/claude-sonnet-5.5` (sidebar-switchable among `AVAILABLE_MODELS` in
`config.py`), guard `anthropic/claude-haiku-4.5`. Haiku 5.5 is blocked by the course API key's
OpenRouter model allowlist, so do not switch the guard to it. Settings come from `.env` via
pydantic-settings (`config.Settings`, cached by `get_settings()`).

**Streamlit state** (`ui/state.py`): `init_state()` creates one settings/tracker/log/client/
pipeline per browser session in `st.session_state`; pages get them through the accessor
functions there. Pages are plain `render()` functions registered in `app.py`; the default page
must not set `url_path`. The sidebar is custom (`st.navigation(position="hidden")` +
`st.page_link`), built in `components.render_sidebar_controls` before `nav.run()` and
`render_sidebar_dynamic` (cost card, security log) after it so the log is current for this run.

**Theme** (`ui/theme.py` + `.streamlit/config.toml`): the native theme in `config.toml` must
mirror `PALETTES[ACTIVE_PALETTE]` (currently `violet-amber`); change both together. The CSS
targets keyed containers (`st.container(key="x")` → `.st-key-x`). `st.html` strips inline SVG,
so the owl mascot is emitted as a base64 data-URI `<img>`. The sidebar brand is pinned via
`position: sticky` on Streamlit's layout wrapper (`:has(> .st-key-brand)`); the collapse chevron
is kept visible through a zero-height sticky header. These selectors depend on Streamlit 1.66
internals, so verify in the browser after upgrading Streamlit.

**Tests** never hit the network: subclass `OpenRouterClient` with a fake `chat`/`chat_structured`
(see `tests/test_pipeline.py`) and build `GuardPipeline(..., llm_guard_enabled=False)`.
