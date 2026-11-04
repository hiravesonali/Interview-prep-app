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
| Prompt Lab (developer tool, linked from Developer settings): 5 system-prompt techniques compared on the same answer, rated, leaderboard | ✅ day 3 |
| LLM-as-a-judge in the Prompt Lab (cross-model judge, rubric, leaderboard column) | ✅ day 3 |
| Developer settings: model, temperature, max tokens, guard toggle, feedback technique | ✅ day 3 |
| Jailbreak experiment: 31 attacks and controls → `docs/jailbreak_experiment.xlsx` | ✅ day 3 |

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
                                   │  LLMGuard     Haiku 4.5 classifier (structured verdict)
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
- `src/interview_app/storage/` — `db.py` (SQLAlchemy engine + tables; `DATABASE_URL` picks SQLite
  locally, Postgres in production), `store.py` (every read/write, scoped to one user; sessions are
  saved after each answer and resumable from the dashboard), `import_json.py` (one-off import of
  the Sprint 1 JSON files).
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

Both are configurable in `.env`. The sidebar offers the three models allowed by the course
brief (`anthropic/claude-sonnet-5.5`, `openai/gpt-6-luna`, `openai/gpt-6.1-sol`).

### Developer settings (sidebar → ⚙️)

Kept in one collapsed expander so a regular user never sees them: model, LLM-guard toggle,
feedback prompt technique, and an **override** toggle for temperature and max tokens. Off, every
task keeps its tuned default (question generation 0.6, feedback and JD analysis 0.2, coaching
0.5). On, the temperature applies to every main-model call and the max-tokens cap applies to the
streamed coaching text only; structured JSON calls keep their own budget because a small cap
would truncate the JSON (see `CallOverrides` in `guard/pipeline.py`).

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

5. **Daily spend cap**: every model call (the guard classifier included) is written to the
   `usage_events` table; once a user's spend since midnight reaches `MAX_DAILY_COST_USD`
   (default $5) the pipeline refuses further calls with a `budget` block. The sidebar's
   per-session soft limit resets on refresh; this one does not, which is what matters once the
   app has a public URL.

Every decision is recorded in the sidebar **Security log** for the current browser session and
in the `security_events` table as a permanent audit trail. Try the **Guard playground** on
the dashboard.

### Jailbreak experiment

`scripts/jailbreak_experiment.py` pushes 31 inputs through the guard: 12 regex-level injections
(classic override, spaced letters, zero-width and full-width unicode, DAN, chat-template tokens,
fake system header, injection hidden in a JD, base64 payload…), 6 semantic attacks with no
keyword to match (paraphrased prompt extraction, role-play framing, score manipulation,
translation trick, off-topic, harmful), 3 secrets, 3 size/empty cases, 2 PII cases and 5
legitimate controls that look suspicious. Results: [docs/jailbreak_experiment.xlsx](docs/jailbreak_experiment.xlsx).

| Run | Result | Notes |
|---|---|---|
| Rules only (offline) | 24 / 31 | the 6 semantic attacks pass the regex layer by design; they need the classifier |
| Rules + LLM guard (`--live`) | 30 / 31 | all semantic attacks blocked by Haiku 4.5; 19 classifier calls cost $0.01 |

The one failure is a documented false positive: a legitimate answer that quotes a chat transcript
(`assistant: hello` at the start of a line) trips the fake-role-line rule. Accepted for now
because the alternative (dropping the rule) opens the "Assistant: ignore the task" injection
hidden inside a job description.

## Prompt engineering: five techniques, one task

The answer-feedback task has five system prompts in `src/interview_app/llm/prompts/feedback/`,
one per technique. Developer settings select which one scores your answers (default: the Lab
winner, role + rubric); the **Prompt Lab** page, linked from the same expander because it is a
developer tool rather than a user feature, runs all five on the same question and answer in parallel, shows score, cost, latency and the full
feedback side by side, and stores your 1-5 usefulness rating in the database (`prompt_lab_runs`). The
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
- Techniques differ more in cost than in verdict: few-shot adds ~1 200 prompt tokens per call;
  chain-of-thought and self-critique cost ~40 % more and take ~45 % longer than zero-shot.

### LLM-as-a-judge

Human ratings are slow and biased by whoever reads first, so the Lab also runs an **LLM judge**
(`llm/prompts/judge_feedback.md`, schema `JudgeVerdict`) over every variant's output. It scores
the *feedback*, not the candidate, on accuracy (claims traceable to the answer), specificity,
actionability and calibration (numbers agree with the text), 1-5 each plus an overall and a
three-sentence rationale. The judge model is selectable; the default is a different model family
(`openai/gpt-6-luna`) than the one writing the feedback, to reduce self-preference bias. Judge
scores are stored with each record and shown in the leaderboard next to the human rating.

### Results (2026-11-03)

`uv run python scripts/run_prompt_lab.py`: feedback by `anthropic/claude-sonnet-5.5`, judged by
`openai/gpt-6-luna`, on the three sample answers (weak / mid / strong) to the same question.
60 calls, $0.26.

Score the technique gave the answer / judge's score of the feedback:

| Technique | Weak | Mid | Strong | Judge avg | Cost / run | Latency | Tokens |
|---|---|---|---|---|---|---|---|
| Zero-shot | 1 / 5 | 2 / 4 | 5 / 4 | 4.33 | $0.0125 | 8.1 s | 2 336 |
| Few-shot | 2 / 5 | 3 / 4 | 4 / 4 | 4.33 | $0.0139 | 7.5 s | 3 520 |
| Chain-of-thought | 2 / 5 | 2 / 4 | 4 / 5 | **4.67** | $0.0173 | 11.5 s | 2 905 |
| Role + rubric | 2 / 5 | 2 / 4 | 4 / 5 | **4.67** | $0.0149 | 10.2 s | 2 803 |
| Self-critique | 2 / 4 | 2 / 4 | 4 / 4 | 4.00 | $0.0170 | 11.8 s | 2 917 |

What the data says:
- Every technique ranks weak < mid < strong, so the task itself is not hard for Sonnet 5.5.
  Differences show in calibration: zero-shot is the most extreme (1 and 5), few-shot is the only
  one that puts the mid answer at 3 (its worked examples include a "solid = 4" case, which pulls
  the scale up), the rest put the mid answer at 2 and the strong one at 4.
- The judge prefers chain-of-thought and role + rubric (4.67) and likes self-critique least
  (4.00): its "critique" record in `analysis` adds length without adding evidence.
- **Winner: role + rubric.** Same judge score as chain-of-thought, 14 % cheaper and 11 % faster,
  and its scores are explainable to the candidate because every dimension has written anchors.
  Chain-of-thought is the runner-up when the reasoning trace itself is wanted in the UI.
- Caveats: three answers to one question and one judge model; the leaderboard in the Lab keeps
  accumulating runs and human ratings, which is the number to trust over time.

### Tuning one setting: temperature

`uv run python scripts/run_prompt_lab.py --temperature-sweep` runs the zero-shot prompt on the
mid answer twice at T = 0.2 and twice at T = 1.0 ($0.05):

| T | Overall | Dimensions (corr / depth / struct / comm) |
|---|---|---|
| 0.2 | 2, 2 | 3/2/3/3 both runs; gaps worded almost identically |
| 1.0 | 2, 3 | 3/2/3/3 both runs; gaps reworded, one new gap ("no automatic checks") |

Dimension scores did not move; at T = 1.0 the overall score swung by one point and the gap list
changed. Scoring stays at 0.2 (stable, reproducible verdicts); coaching keeps 0.5 for variety.

## Scripts

| Script | What it does |
|---|---|
| `scripts/run_prompt_lab.py` | 5 techniques × 3 sample answers (+ judge) → `prompt_lab_runs` table and a Markdown table; `--temperature-sweep`; `--dry-run` |
| `scripts/jailbreak_experiment.py` | 31 attack/control inputs through the guard → `docs/jailbreak_experiment.xlsx`; `--live` adds the LLM guard |
