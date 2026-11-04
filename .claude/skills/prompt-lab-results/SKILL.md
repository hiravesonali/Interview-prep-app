---
name: prompt-lab-results
description: Rerun the Prompt Lab comparison (five feedback prompt techniques plus LLM judge, and the temperature sweep) and bring README's "Results" section and the default grader back in line with the new numbers. Use this whenever a feedback prompt under llm/prompts/feedback/ or the judge prompt changes, when the feedback or judge model changes, when the user asks to "rerun the lab", "update the results", "refresh the leaderboard", or asks which technique wins now. The README table is a course deliverable, so stale numbers are a real defect.
---

# Prompt Lab results: rerun and record

The course asks for five system prompts with different techniques, a comparison, an LLM judge,
and one tuned setting. The evidence for all four lives in README's **Results** and **Tuning one
setting** sections, filled from `scripts/run_prompt_lab.py`. Whenever the prompts, the models or
the judge change, those numbers stop describing the app, and a reviewer who reruns the script
will notice. This skill is the procedure for keeping them honest.

## 0. Decide whether a rerun is needed, and get an OK

A full run costs real money (the 2026-11-03 run: 60 calls, about $0.26; the temperature sweep
adds about $0.05). Rerun when a feedback prompt, `judge_feedback.md`, `SAMPLE_ANSWERS`, the
default model or the judge model changed. Do not rerun for UI or README wording changes.

Always show the plan first and wait for Sonali's go-ahead, because it spends her API budget:

```bash
uv run python scripts/run_prompt_lab.py --dry-run     # prints models + number of calls, calls nothing
```

## 1. Run

```bash
uv run python scripts/run_prompt_lab.py 2>&1 | tee <scratchpad>/lab_run.txt
uv run python scripts/run_prompt_lab.py --temperature-sweep 2>&1 | tee <scratchpad>/lab_sweep.txt
```

Options: `--model`, `--judge-model` (default: the first course model that is not the feedback
model, so the judge is a different family), `--no-judge`. Each run appends to
the `prompt_lab_runs` table (SQLite at `data/hoot.db` locally), which the Lab page's leaderboard reads, so the leaderboard accumulates
history; that is intended. Human ratings stay empty: Sonali adds those in the Lab UI.

The script prints the per-answer score matrix, the averages table, and the total cost. If a
technique shows `err`, fix the cause (usually a schema or `max_tokens` problem; reasoning
models need a generous budget) and rerun before recording anything. Partial tables are worse
than old tables.

## 2. Update README

Edit `README.md` under `### Results (<date>)`; keep this shape so runs stay comparable:

```markdown
### Results (YYYY-MM-DD)

`uv run python scripts/run_prompt_lab.py`: feedback by `<model>`, judged by `<judge model>`,
on the three sample answers (weak / mid / strong) to the same question. <N> calls, $<cost>.

Score the technique gave the answer / judge's score of the feedback:

| Technique | Weak | Mid | Strong | Judge avg | Cost / run | Latency | Tokens |
|---|---|---|---|---|---|---|---|
| Zero-shot | 1 / 5 | ... |

What the data says:
- <ranking: does every technique order weak < mid < strong?>
- <calibration: which technique drifts, and why, pointing at the prompt text>
- **Winner: <technique>.** <judge score, cost and latency relative to the runner-up, and why it is the better default for a candidate>
- Caveats: three answers to one question and one judge model; the Lab leaderboard with human ratings is the number to trust over time.
```

Merge the script's two tables into the one README table (per-answer "score / judge" cells plus
the averages columns). Bold the best judge average. Write the "What the data says" bullets from
the new numbers, not by editing the old sentences: each claim must be visible in the table.
Update the temperature table the same way when the sweep was rerun, and keep the one-line
decision after it (scoring temperature vs coaching temperature) consistent with `config.py`.

Also refresh the sentence under **Prompt engineering** that names the default grader and the
Results date mentioned in `CLAUDE.md`'s Product section.

## 3. If the winner changed

The winner is the default grader for real practice sessions. Change all three together:

- `src/interview_app/ui/state.py`: `feedback_technique` default.
- `README.md`: the "default: the Lab winner, ..." phrase and the Results bullets.
- `PLAN.md`: the decision row for the Prompt Lab (section 8, item 8) and add a dated line to
  **6. Decisions** saying what changed and why. Decisions live in PLAN.md so they can be
  defended in the review.

Then run `uv run pytest` (there is a test that checks the default technique exists) and
`uv run ruff format .`.

## 4. Report

Tell Sonali: the models used, calls and cost, the winner and whether it changed, and which files
you edited. Prompts 02-05 are hers to tune; if a result suggests a prompt change, say what the
data shows and let her decide the wording.
