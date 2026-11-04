---
name: streamlit-verify
description: Run Hoot (the Streamlit app) and check a UI change in a real browser, with screenshots of each page and the browser console. Use this whenever a change touches ui/ (pages, components, theme.py, .streamlit/config.toml), the sidebar, navigation, CSS selectors, or after a Streamlit upgrade, and whenever the user asks to "run the app", "check it in the browser", "take a screenshot", or "does it still look right". Tests cannot see layout or CSS, so a UI change is not verified until this skill has been run.
---

# Streamlit verify: run Hoot and look at it

Hoot's theme works by targeting Streamlit's internal DOM (`.st-key-*` containers, `data-testid`
attributes, a `:has()` selector that pins the sidebar brand). Those selectors are not covered by
`pytest`, and they can silently stop matching after a CSS edit or a Streamlit upgrade. The only
way to know a UI change worked is to render the page and look.

## 1. Start the server (or reuse the one that is running)

```bash
lsof -nP -iTCP:8501 -sTCP:LISTEN          # something listening? Sonali probably has it open
uv run streamlit run app.py               # otherwise; run in the background, it blocks
```

Streamlit re-runs the script on every file save, so a running server already shows your edit.
Do not start a second server on 8501; if you need your own, pass `--server.port 8502` and use
`--base http://localhost:8502` below. Kill only a server you started.

## 2. Screenshot every page

```bash
uv run --with playwright python .claude/skills/streamlit-verify/scripts/screenshot.py \
    --out <scratchpad>/shots [--pages home,jd] [--sidebar-collapsed] [--base http://localhost:8501]
```

`--with playwright` installs Playwright into a throwaway environment; it is deliberately not a
project dependency. Chromium is already in `~/Library/Caches/ms-playwright`; if Playwright
complains that the browser is missing, run `uv run --with playwright playwright install chromium`.

The script waits for the server, loads each page by its URL path, waits until Streamlit's
"Running" indicator is gone, saves a full-page PNG per page, and prints browser console errors.
It never clicks a button, so it never triggers an LLM call or spends money. Each page gets a
fresh browser context, because Streamlit remembers a collapsed sidebar across reloads. The
404s Streamlit itself produces when a sub-page URL is opened directly (`/practice/_stcore/health`)
are filtered out; anything else printed is real. Then open the PNGs with the Read tool and
actually look at them.

| Page | URL path | What to look at |
|---|---|---|
| home | `/` | hero card with two buttons, role grid, recent sessions, playground |
| practice | `/practice` | role selector or question card (`st-key-question_card`), mode toggle |
| jd | `/jd` | text area and analyse button; results cards after a run |
| lab | `/lab` | input card (`st-key-lab_input`), Options expander, Run button, leaderboard table; technique cards only after a run |

On every page also check the sidebar: owl brand stays pinned at the top when the page scrolls,
user menu shows Dashboard / Practice session / JD analyzer only, the Developer settings expander
holds model, technique, temperature, max-tokens and the Prompt Lab link, cost card and security
log at the bottom. Take a `--sidebar-collapsed` shot when the brand or collapse chevron changed:
the chevron is kept visible through a zero-height sticky header and is easy to break.

## 3. What a broken selector looks like

Streamlit changes its DOM between releases. The symptoms are quiet: a card loses its rounded
background, the brand scrolls away with the page, the collapse chevron disappears, fonts fall
back to sans-serif. When you see one of those, inspect the live DOM instead of guessing:

```bash
uv run --with playwright python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); pg.goto('http://localhost:8501', wait_until='networkidle')
    pg.wait_for_selector('[data-testid=\"stStatusWidget\"]', state='detached')
    print(pg.locator('[data-testid=\"stSidebar\"]').inner_html()[:3000]); b.close()"
```

Fix the selector in `src/interview_app/ui/theme.py`, then re-shoot. If a Streamlit upgrade
caused it, note the new version and the selector in CLAUDE.md's Theme paragraph so the next
upgrade is checked too.

## 4. Pages that need the API key

Home, the empty practice and JD pages, and the Lab's input form render without a key. Anything
that calls the model (generate questions, analyse a JD, run the Lab) needs `OPENROUTER_API_KEY`
in `.env` and costs money. Do not drive those flows from a script without asking; when a flow
has to be checked end to end, Sonali clicks and you read the screenshot or the security log.

## 5. Before saying "verified"

- `uv run pytest` and `uv run ruff check . && uv run ruff format --check .` still pass.
- Screenshots of every page the change could affect were taken after the final edit and looked
  at, with no new console errors.
- Report what you looked at and what you saw, not only that the script ran. Attach the PNG paths.
