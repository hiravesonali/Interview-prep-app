# Interview Practice App — Architecture & Delivery Plan

Status: APPROVED 2026-11-03. Day 1 (scaffold, client, guard, dashboard), Day 2 (JD analyzer, practice loop, history), UI redesign and Prompt Lab (5 feedback prompt variants, parallel comparison, ratings, leaderboard) delivered.
Note: guard model changed to Haiku 4.5 because the course API key's OpenRouter guardrail allowlist blocks Haiku 5.5.
Changes in v2: main model = Sonnet 5.5; prompt-technique lab (course requirement); RAG phase 2 with embedding model options.
Changes in v3 (2026-11-03, after reviewing the app against the course brief): see §8.

## 1. Goal
A personal interview-prep tool for technical roles (Full-stack, Frontend, Backend, AI Engineer, AI Agent Developer, Product Engineer, ...).
Two core features, one dashboard, every LLM call routed through a security guard to OpenRouter.

## 2. Features

### F1 — Practice session (question by question)
Flow:
1. Pick role (preset chip or free-text title), difficulty (junior/mid/senior), question mix (technical / system design / behavioural), count (default 10).
   Optional: questions come from a JD analysis (see F2 handoff).
2. App generates the question set once (structured output: topic, question, what a strong answer covers, 3 progressive hints).
3. Session state machine, one question at a time:
   - **Guided mode** (default): AI asks the question, then coaches step by step — "clarify what is asked" → "structure your answer (e.g. STAR / problem-approach-tradeoffs)" → "key points to hit" → user writes answer → feedback.
   - **Mock mode**: AI only asks; user answers; feedback is deferred to the end summary.
4. Feedback per answer (structured): score 1-5 on correctness, depth, structure, communication; strengths; gaps; a model answer; follow-up question an interviewer would ask.
5. End-of-session summary: scores by topic, weakest areas, what to revise, option to retry weak questions.
6. Session saved locally (JSON) so history is available in later sessions.

### F2 — Job description analyzer
Input: pasted JD (capped ~8k chars) + optional target title.
Output (structured, rendered as cards/tabs):
- Role snapshot (seniority, domain, team signals)
- Must-have skills vs nice-to-have (grouped: languages, frameworks, infra, AI/ML, soft)
- Likely interview questions, grouped (technical, system design, behavioural, role-specific)
- Preparation plan, day by day (7 or 14 days, chosen by user), each step with a concrete task
- Questions to ask the interviewer + red flags
- Button **"Practice these questions"** → opens F1 pre-loaded with the JD's questions (the connecting feature)

### Dashboard (home)
- Hero with two feature cards (Practice / Analyze JD)
- Role chips: Full-stack Developer, Frontend Developer, Backend Developer, AI Engineer, AI Agent Developer, Product Engineer, Data Engineer, Platform/DevOps (editable list in `roles.yaml`) + free-text job title input
- Recent sessions list (from local history)
- Sidebar (all pages): model selector, guard mode, token/cost meter for this session, security log

## 3. Architecture

```
Streamlit UI (pages)  ──►  features/* (orchestration)  ──►  guard.InputGuard
                                                               │ allowed? → llm.client (OpenRouter via openai SDK)
                                                               ▼
                                                           guard.OutputGuard  ──►  pydantic models  ──►  UI
```

Request pipeline for every LLM call:
1. **InputGuard** (deterministic, free, unit-tested): length caps, prompt-injection regex set (OWASP cheat-sheet patterns: "ignore previous instructions", role override, system-prompt extraction, encoding tricks), secret/PII detection (API keys, emails/phones in JDs are redacted), topic scope check (must be interview/career related).
2. **LLM classifier guard** (optional toggle, cheap model): returns `{allowed, category, reason}` via structured output. Catches semantic attacks the regex misses.
3. **OpenRouter call** with system prompt from versioned prompt files; structured output (`response_format` json_schema) for questions/analysis/feedback; streaming for coaching text.
4. **OutputGuard**: schema validation (pydantic), system-prompt leak check, strip unsafe markup; on failure → one retry with a repair instruction, then a safe fallback message.
5. Every decision is appended to a **security log** shown in the sidebar (good for the demo/review).

Defense in depth: also enable OpenRouter's native Guardrails (prompt-injection block + spend budget) on the API key in the dashboard — zero code, documented in README.

### Project layout (uv)
```
Interview-practice-app/
  pyproject.toml            # uv-managed; deps: streamlit, openai, pydantic, pydantic-settings, pyyaml; dev: pytest, ruff
  .env.example              # OPENROUTER_API_KEY, DEFAULT_MODEL, GUARD_MODEL
  app.py                    # entry: st.navigation → pages
  src/interview_app/
    config.py               # Settings (pydantic-settings)
    models.py               # pydantic schemas: Question, QuestionSet, AnswerFeedback, JobAnalysis, PrepPlan, GuardDecision
    llm/client.py           # OpenRouter wrapper: chat(), chat_structured(), stream(); retries; usage+cost accounting
    llm/prompts/*.md        # versioned system prompts (one file per task)
    guard/input_guard.py    # rules + patterns
    guard/llm_guard.py      # classifier
    guard/output_guard.py
    guard/pipeline.py       # guarded_call() — the single choke point all features use
    features/practice.py    # question generation, session state machine, feedback, summary
    features/jd_analyzer.py
    storage/history.py      # JSON persistence in ./data/sessions
    data/roles.yaml         # role presets + seed topics
    ui/pages/home.py, practice.py, jd_analyzer.py
    ui/components.py        # cards, score badges, cost meter, security log
  tests/                    # guard rules, schema parsing, state machine (no network)
  README.md
```

### Key tech decisions
| Decision | Choice | Why |
|---|---|---|
| OpenRouter client | `openai` SDK with `base_url=https://openrouter.ai/api/v1` | standard, supports structured outputs + streaming, easy to swap models |
| Main model | `anthropic/claude-sonnet-5.5` ($2 in / $10 out per 1M) — decided | higher capability for coaching, feedback and JD analysis; supports structured outputs + streaming |
| Guard classifier model | `anthropic/claude-haiku-4.5` ($1 / $5 per 1M) | Haiku 5.5 is blocked by the key's model allowlist; 4.5 is the cheapest allowed Anthropic model. Configurable via `GUARD_MODEL` |
| Embeddings (phase 2 RAG) | `qwen/qwen3-embedding-8b` default; `openai/text-embedding-3-small` / `-large` selectable | course-provided options; all via OpenRouter `/embeddings` so one API key |
| Cost control | per-call usage logged, session cost meter, `MAX_SESSION_COST` soft limit warning | Sonnet is ~20x Haiku; a 10-question guided session ≈ 40-60k tokens ≈ $0.30-0.60 |
| Structured outputs | pydantic v2 → json_schema | reliable rendering, testable, course topic |
| State | `st.session_state` + JSON files (Sprint 1) → SQLAlchemy, SQLite local / Postgres prod (§9) | simple first; one code path when deployed |
| Navigation | `st.navigation` multi-page | clean dashboard → feature routing |
| Python | 3.12 via uv | stable for Streamlit 1.66 |

## 3b. Prompt-technique lab (course requirement: 5+ system prompts, compare)
Applied to the **answer-feedback task** (most judgement-heavy, so differences are visible). Five system prompt variants, each a separate file under `llm/prompts/feedback/`:

| # | Technique | File | What it does |
|---|---|---|---|
| 1 | Zero-shot | `01_zero_shot.md` | plain instruction: evaluate the answer, return the feedback schema |
| 2 | Few-shot | `02_few_shot.md` | adds 3 worked examples (weak / ok / strong answer → feedback) |
| 3 | Chain-of-Thought | `03_chain_of_thought.md` | model fills an `analysis` field (what was asked, what was covered, what was missed) *before* scoring |
| 4 | Role + rubric | `04_role_rubric.md` | senior-interviewer persona + explicit 1-5 rubric per dimension with anchors |
| 5 | Self-critique (reflexion) | `05_self_critique.md` | draft feedback → critique the draft against the rubric → final feedback |

Comparison mechanics:
- Sidebar selector picks the active technique for live sessions.
- **Prompt Lab page**: paste (or pick from history) one question + answer, run all 5 variants, show results side by side with tokens, cost and latency, and a 1-5 "usefulness" rating you give each. Ratings are stored in `data/prompt_lab.json`.
- README gets a short results table (which technique won and why) — this is the "check which one works best" evidence for the review.
- Other tasks use a single prompt each but still name their technique: question generation = few-shot + structured output; JD analysis = CoT + structured output; guided coaching = role prompting with step constraints.

## 3c. RAG (phase 2, after Sprint 1 unless the brief requires it now)
Use case that actually helps interviews: a **personal knowledge base** — your CV, project notes (Doratics, Wittypen, Expondo), past answers and saved JD analyses. The coach then asks "tell me about X" questions grounded in your real experience and feedback can say "you did this at Doratics, mention it".
Design slot (no code in Sprint 1): `storage/vector_store.py` (local, e.g. `chromadb` or sqlite + numpy), `rag/ingest.py` (chunk markdown/PDF → embeddings via OpenRouter), `rag/retrieve.py` (top-k context injected into the practice and feedback prompts). Embedding model selectable; default `qwen/qwen3-embedding-8b`.

## 3d. Visual design (added 2026-11-03)
Reference: Huru-style dashboard. Own brand: **Hoot**, an owl mascot with coral glasses (inline SVG,
`ui/theme.py`). Palette = Tailwind tokens, three options defined in `PALETTES` (violet-amber chosen by Sonali;
indigo-coral and teal-rose as alternatives, previewed at https://claude.ai/artifact/5EMQkvfcES1pPdjc3MYRWZ).
Font: Plus Jakarta Sans (Google Fonts woff2 via `[[theme.fontFaces]]`). Sidebar: brand pinned (sticky),
rest scrolls; 12px radius.
Implementation: native Streamlit theme in `.streamlit/config.toml` + CSS targeting keyed containers;
own sidebar menu (`st.navigation(position="hidden")` + `st.page_link`), hero and role grid on the dashboard.
Practice setup (2026-11-05): three numbered steps instead of a flat form (role preset dropdown with a
custom-title option and the preset's topics, mode radio with captions, difficulty as segmented buttons
with a plain-English hint, question types as pills with human labels, slider with a time estimate, a live
summary line and a "Start practice" button). No `st.form`, so the summary reacts to every change; no
LLM call happens before the button.
JD analyzer (2026-11-05): same two-step input card; results as a "role snapshot" card (badges, four stats,
practise / analyse-another buttons) over four tabs: skills as must-have vs nice-to-have chips, questions as
compact cards grouped by type, prep plan as day cards with task checkboxes, ask & flags in two columns.
The JD prompt now carries the same 25-word, single-ask question wording rule and must name the JD's actual
stack; the schema and the hand-off to practice are unchanged.

## 4. Suggestions beyond the brief (recommended, small cost)
1. Guided vs Mock mode (F1) — mock mode is what real interviews feel like.
2. JD → Practice handoff — makes the two features one product.
3. Session history + summary — needed for "use this for my real interviews".
4. Token/cost meter in sidebar — ties into the course's cost/tokens topic.
5. Security log panel — makes the guard visible in the demo.
Later (not in Sprint 1): voice answers (OpenRouter STT), CV upload for skill-gap analysis, eval script scoring feedback quality, SQLite + search of history.

## 5. Delivery plan (MVP Thu Nov 6, polish Fri Nov 7)
- **Tue Nov 3**: scaffold with uv, config, OpenRouter client (+cost accounting), InputGuard + OutputGuard + tests, dashboard skeleton with role chips.
- **Wed Nov 4**: JD analyzer end-to-end (structured output → cards); question generation + ask/answer/feedback loop.
- **Thu Nov 5**: guided mode steps, JD→practice handoff, session summary, JSON history, LLM guard toggle, security log; the 5 feedback prompt variants + sidebar selector. **MVP done.**
- **Fri Nov 6**: Prompt Lab page + run the comparison and record results; README (architecture, security design, prompt-technique results, how to run); tests pass; UI polish; demo run.
- **Phase 2 (week 3 of the course)**: RAG personal knowledge base.

## 6. Decisions
- Main model: `anthropic/claude-sonnet-5.5` (decided by Sonali). Sidebar list = the three course models
  (`anthropic/claude-sonnet-5.5`, `openai/gpt-6-luna`, `openai/gpt-6.1-sol`).
- Guard classifier: `anthropic/claude-haiku-4.5` (Haiku 5.5 is blocked by the key's allowlist).
- Guard design: rule-based + Haiku classifier + OpenRouter native guardrails (403 → logged block). Approved.
- Local JSON history on by default. Approved.
- Embeddings: `qwen/qwen3-embedding-8b` default, OpenAI small/large selectable (phase 2).
- RAG, LangChain, deployment: after Sprint 1 (deployment + database agreed 2026-11-04, see §9).
- Working style: Claude scaffolds and documents decisions; Sonali writes/tunes the prompt variants herself.
- Question wording (2026-11-05): questions stay a ten-question structured batch, but each `question`
  must be 25 words or fewer, ask one thing, use plain English, and match the difficulty ladder
  (junior = definitions, mid = how/why or comparison, senior = one-sentence trade-off). Rules and
  BAD/GOOD pairs live in `llm/prompts/question_generation.md`; the schema and hints are unchanged.

## 7. Still open
Nothing blocking. Image generation and open-source models (optional tasks) are skipped for Sprint 1.

## 8. v3 — gap closure after the brief review (2026-11-03)
Checked the app against the course task description. Core requirements were met; these items were
added because they are explicitly listed optional tasks and cheap given the existing structure:

| # | Item | Brief task | Design |
|---|---|---|---|
| 1 | Model list fixed to the course models | "Choose one of the following models" | `AVAILABLE_MODELS` = Sonnet 5.5, gpt-6-luna, gpt-6.1-sol. Haiku 4.5 stays guard-only. |
| 2 | Developer settings: temperature + max-tokens sliders | Medium: "all model settings as sliders" | `GuardPipeline.overrides` (`CallOverrides`): when set, temperature applies to every main-model call; max tokens applies to text calls (`chat`/`stream`) only, because structured calls size their own JSON budget and a small cap would truncate them. The guard classifier is never affected. Default = per-task values. |
| 3 | LLM-as-a-judge in the Prompt Lab | Hard: "assess the performance of your prompt via LLM-as-a-judge" | `judge_feedback.md` prompt + `JudgeVerdict` schema (accuracy, specificity, actionability, calibration, overall, rationale). Runs once per variant in parallel after the comparison; judge model is selectable (default gpt-6-luna, a different family than the one that wrote the feedback, to reduce self-preference bias). Judge score is stored per record and shown in the leaderboard next to the human rating. |
| 4 | Jailbreak experiment → Excel | Medium: "try to jailbreak your own application … results in an Excel sheet" | `scripts/jailbreak_experiment.py`: ~30 attack and control inputs through the rule guard (offline) and, with `--live`, the LLM guard. Writes `docs/jailbreak_experiment.xlsx` (results + summary sheet). |
| 5 | Prompt Lab results recorded | Core: "check which one works best" | `scripts/run_prompt_lab.py` runs all variants on the three sample answers (+ judge) and appends to `data/prompt_lab.json`; the README Results table is filled from it. Human usefulness ratings are added by Sonali in the Lab UI. |
| 6 | Temperature experiment | Easy: "tune one model setting and compare" | Same script, `--temperature-sweep`: zero-shot at 0.2 and 1.0, twice each; score spread recorded in the README. |
| 8 | Prompt Lab demoted to a developer tool | Medium: "keep the developer settings separate from the user experience" | The user menu shows Dashboard, Practice, JD analyzer. The Lab is linked from the Developer settings expander (under "Tools"); its technique picker and judge settings sit in an Options expander so the visible flow is pick input → run → rate → save. The Lab winner (role + rubric) is the default grader. |
| 7 | Small fixes | — | README guard model name; mock-mode scoring errors are shown instead of swallowed; guided mode collects the optional note for the coach; sessions are saved after every answer so an abandoned session is resumable from the dashboard. |

## 9. v4 — persistence and deployment (agreed 2026-11-04, first post-Sprint 1 work)

Context: today finished sessions are JSON files in `data/sessions/`, Prompt Lab runs live in
`data/prompt_lab.json`, and the cost meter and security log are in memory and reset on every
browser refresh. All data is single-user and document-shaped (nested pydantic models, no joins).

| Decision | Choice | Why | Rejected |
|---|---|---|---|
| Database | SQLAlchemy 2.0; `DATABASE_URL` selects the engine: `sqlite:///data/hoot.db` locally, hosted Postgres (Neon free tier) in production, in-memory SQLite in tests | one code path (12-factor, same convention as Node); no local setup; tests stay offline | JSON files on a persistent volume (no querying, ties us to a host with disks); local Postgres in Docker (slower dev loop for no gain); SQLModel (dual pydantic/SQLAlchemy models surprise on nested documents) |
| Schema | "document with index": per table a few scalar columns for listing/filtering plus one JSON column holding the full pydantic dump. Tables: `sessions`, `prompt_lab_runs`, `security_events`, `usage_events`. Every table has `user_id` from day one | pydantic models stay the source of truth; table shape rarely changes, so no Alembic until the first real migration | ten normalized tables for data never queried by field |
| New persisted data | `security_events` (audit trail of guard decisions) and `usage_events` (per-call cost → per-user **daily** cap, default $2, plus a **global** daily cap, default $20, both enforced in the pipeline; an OpenRouter key spend limit is the last line) | the per-browser-session cap resets on refresh; with a public URL that is a real hole | — |
| Host | Streamlit Community Cloud (git-push deploy, secrets UI, free). Fly.io/Railway with a Dockerfile is the Phase 2 option if an always-on process, SQLite on a volume, or Docker experience is wanted | right size for a one-person app; the reviewer can open a link | Render free tier (spins down, ephemeral disk); HF Spaces (no persistent disk) |
| Access | **Revised 2026-11-05**: public demo. Streamlit `st.login` (Google OIDC) stays, but `ALLOWED_EMAILS="*"` admits any Google account; a comma-separated list turns it back into a private allowlist. `user_id` = the signed-in email; `"local"` without auth | the reviewer and CV readers must get in without setup; sign-in is kept for identity (per-user cap, private histories, audit trail), not exclusivity | no sign-in at all (users indistinguishable: shared histories, no per-user cap, anonymous attacks) |
| Production safety | `APP_ENV=prod` forces the LLM guard to fail closed and requires auth | fail-open is right for local dev, wrong for a public app | — |

Confirmed 2026-11-04 after discussion: Streamlit Community Cloud stays the host (native Streamlit
hosting, git-push deploy, secrets UI, works with `st.login`); Neon stays the Postgres provider over
Supabase because only Postgres is needed (Supabase Auth is not an OIDC provider for `st.login`),
Neon auto-wakes from idle while a Supabase free project pauses after a week, and Neon's pooled
URL works from Community Cloud without the IPv4 pooler detour. Switching is one URL in secrets.

Migration: a one-off script imports the existing `data/sessions/*.json` and `data/prompt_lab.json`
into the database so the Sprint 1 history and the Prompt Lab results (a course deliverable) survive.
