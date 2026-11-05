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

5. **Daily spend caps**: every model call (the guard classifier included) is written to the
   `usage_events` table. The pipeline refuses further calls with a `budget` block once a user's
   spend since midnight reaches `MAX_DAILY_COST_USD` (default $2) or everyone's reaches
   `MAX_DAILY_COST_TOTAL_USD` (default $20). The per-user cap bounds one person, the global cap
   bounds the worst day of a public deployment; both are persisted, unlike the sidebar's
   per-session soft limit. A spend limit on the OpenRouter key is the last line of defence.
6. **Sign-in for identity, not exclusivity**: the public deployment admits any Google account
   (`ALLOWED_EMAILS="*"`), so the reviewer or a CV reader just signs in. The identity is what
   makes the per-user cap, private histories and the audit trail work; a comma-separated list
   turns the same gate into a private allowlist.

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

## Deployment

Production = **Streamlit Community Cloud** (host) + **Neon** (Postgres) + Google sign-in,
open to any Google account (`ALLOWED_EMAILS = "*"`).
Decisions and alternatives are in `PLAN.md` §9. Local development needs none of this: without
an `[auth]` block the app runs as the single `local` user against `data/hoot.db`.

### 1. Database (Neon)

1. Create a free project at neon.com (region near you), database `hoot`.
2. Use the **pooled** connection string (host contains `-pooler`) as `DATABASE_URL`, exactly as
   Neon shows it (`postgresql://USER:PASSWORD@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require`).
   The app pins the psycopg driver itself. With the Neon CLI, `neon init` writes this into `.env`.
3. Check it from your machine (creates the tables and prints the row counts):
   ```bash
   uv run python scripts/check_db.py                     # uses DATABASE_URL from .env
   uv run python scripts/import_json_data.py             # optional: Sprint 1 history → Neon
   ```
   Note: once `.env` holds the Neon URL, local runs use Neon too (as user `local`); remove the
   line or set `DATABASE_URL=sqlite:///data/hoot.db` to go back to the local file.

### 2. Google sign-in (OAuth client)

1. Google Cloud Console → APIs & Services → Credentials → **Create credentials → OAuth client ID**,
   type **Web application**. (First time: configure the consent screen as *External*, add
   yourself as a test user, or publish it: with only the basic openid/email/profile scopes
   no verification is needed and any Google account can sign in. Publishing asks for a
   privacy-policy URL: the app serves one at `https://YOUR-APP.streamlit.app/privacy`,
   readable without sign-in.)
2. Authorised redirect URIs: `http://localhost:8501/oauth2callback` for local tries and
   `https://YOUR-APP.streamlit.app/oauth2callback` once you know the app URL.
3. Note the client ID and secret. Generate a cookie secret:
   `python -c "import secrets; print(secrets.token_hex(32))"`.

To try sign-in locally, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
(gitignored), fill it in and restart the server. `ALLOWED_EMAILS` is `*` for any Google account
or a comma-separated list; an empty value admits nobody.

### 3. Deploy on Community Cloud

1. share.streamlit.io → **Create app** → from GitHub: this repo, branch `main`, entrypoint
   `app.py`. Community Cloud installs from `uv.lock` and defaults to Python 3.12.
2. **Advanced settings → Secrets**: paste the filled-in contents of
   `.streamlit/secrets.toml.example` with `APP_ENV = "prod"`, the Neon URL, `ALLOWED_EMAILS = "*"` and
   the `[auth]` block with the production `redirect_uri`. Root-level keys become environment
   variables, which is how `config.Settings` reads them.
3. Deploy, then open the URL: you should see the sign-in card, Google, then the dashboard with
   your email in the sidebar. `APP_ENV=prod` has forced the LLM guard to fail closed and the
   daily spend cap (`MAX_DAILY_COST_USD`) is enforced per signed-in user.

What to expect: the app sleeps after a while without visitors and wakes on the next visit;
Neon suspends its compute when idle and resumes on the first query (a second or two).

## Scripts

| Script | What it does |
|---|---|
| `scripts/check_db.py` | Connect to `DATABASE_URL`, create missing tables, print row counts: the pre-deploy check for a hosted Postgres URL |
| `scripts/import_json_data.py` | Import the Sprint 1 JSON files (`data/sessions/*.json`, `data/prompt_lab.json`) into `DATABASE_URL`; idempotent |
| `scripts/run_prompt_lab.py` | 5 techniques × 3 sample answers (+ judge) → `prompt_lab_runs` table and a Markdown table; `--temperature-sweep`; `--dry-run` |
| `scripts/jailbreak_experiment.py` | 31 attack/control inputs through the guard → `docs/jailbreak_experiment.xlsx`; `--live` adds the LLM guard |
