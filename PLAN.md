# Interview Practice App — Architecture & Delivery Plan

Status: APPROVED 2026-11-03. Day 1 (scaffold, client, guard, dashboard) and Day 2 (JD analyzer, practice loop, history) delivered.
Note: guard model changed to Haiku 4.5 because the course API key's OpenRouter guardrail allowlist blocks Haiku 5.5.
Changes in v2: main model = Sonnet 5.5; prompt-technique lab (course requirement); RAG phase 2 with embedding model options.

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
| State | `st.session_state` + JSON files | simple; SQLite later if needed |
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

## 6. Decisions so far
- Main model: `anthropic/claude-sonnet-5.5` (decided by Sonali).
- Guard classifier on Haiku 5.5 (proposed, pending OK).
- Embeddings: `qwen/qwen3-embedding-8b` default, OpenAI small/large selectable (phase 2).
- Prompt requirement: 5 system prompts with different techniques, compared in a Prompt Lab.

## 7. Still open
1. Guard design (rule-based + Haiku classifier + OpenRouter native guardrails) — OK?
2. Local JSON history on by default — OK?
3. RAG: phase 2 after Sprint 1, or does the brief require it in Sprint 1?
4. Any other items in the brief (security checks, docs, deployment)?
5. Working style: I scaffold and document decisions; you write/tune the prompt variants yourself (you must defend them in review) — OK?
