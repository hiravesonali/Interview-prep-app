# LLM critique of Hoot

Generated 2026-11-05 by `anthropic/claude-sonnet-5.5` via `scripts/llm_critique.py` (23,584 prompt + 11,678 completion tokens, $0.1639). Input: README, guard pipeline, prompts, practice feature.

## Usability

- **Unfocused README pitch.** The header says "Two features, one dashboard", but the table lists the practice session, JD analyzer, Prompt Lab, resume builder and rubric, and its status column mixes "day 1–2" with "2026-11-05". A first-time reviewer can't tell what the product is. Rewrite the opener to name the user-facing features, move Prompt Lab and the sprint log into a "Developer / course notes" section, and add one screenshot of the practice flow.

- **Slow default feedback style.** Your own style sweep shows detailed feedback is about 4x longer, 2.5x costlier and 3x slower (15–19 s vs 5–7 s), and the judge rates concise as well or better. Yet `style` defaults to `"detailed"` in `PracticeSession`, even for mock mode, where a candidate is on the clock. Default mock sessions to concise and keep detailed for guided mode.

- **Opaque block messages.** A block returns "Input matches prompt-injection patterns." even though the guard knows which rule fired (`fake_role_line`, `dev_mode`). The README admits a legitimate answer quoting `assistant: hello` is rejected, and the user gets no hint what to change. Map each label to a plain-language fix ("lines starting with 'Assistant:' are treated as instructions; quote them inline instead"). A "send as quoted text" option is also worth considering.

- **Surprise daily cap.** `check_budget` refuses with "Try again tomorrow" once the limit hits, and the reset is "since midnight" on the server's clock. A user mid-session can lose the ability to get feedback with no warning, and a global-cap block looks identical to a personal one. Show "$0.40 left today, resets at 00:00 UTC" next to the existing session cost meter, and warn at 80%.

- **Trust-building design.** Redacting emails and phones instead of blocking, telling the user ("Redacted email before sending"), keeping contact details out of the resume model, and saving sessions after each answer so they can be resumed all reduce anxiety. Keeping temperature and max tokens behind one collapsed "Developer settings" expander is also the right call. Keep this pattern and apply it to the block messages above.

## Security

- **Structured output isn't sanitized.** The README says the output guard "strips active HTML, redacts secrets", but `GuardPipeline.structured` calls `self.check_output(result.raw, ...)` and ignores the returned sanitized text. The comment says the validated pydantic object is what gets rendered. So feedback, JD analysis and resume content, which are most of the app, get only the leak block, not redaction. Run the same HTML and secret scrub over the string fields of the validated model, or fail the call when the scrub changes the raw text. Narrow the README claim in the meantime.

- **Weak leak check, late stream check.** `OutputGuard` only blocks a verbatim echo of a system-prompt line of 60+ characters. A paraphrase, translation or line-by-line split passes, and the README's own "translation trick" attack shows that class exists. `stream()` runs the check after every delta has been yielded, so a leak is already on screen before `GuardBlocked` fires. The block decision also records `line[:40] + "..."` of the system prompt, which goes to the sidebar log and `security_events`. Buffer the short coaching stream (it is capped at 180 words), or check at sentence boundaries, and log a hash or line index instead of prompt text.

- **Trusted slots carry untrusted data.** Only the `{ input }` value is guard-checked. `role` is rendered into the system prompt via `render_prompt(..., role=role)`, and in `evaluate_answer` it is not re-checked. `topics` go into the generation template unguarded. Questions derived from a pasted JD flow into the coach and feedback templates as "app-authored context", so a JD injection that survives once becomes trusted later. Delimiters like `<candidate_answer>` and `<user_input>` are not escaped, so an answer containing `</candidate_answer>` can break out. I couldn't see `llm_guard.py`, so check that case there too. Strip or escape closing tags in user text, run `topics` and JD-derived questions through `check_input`, and put `role` in the user turn rather than the system prompt.

- **Regex false positives from the compact scan.** Normalizing with NFKC and stripping zero-width characters is solid, and the whitespace-stripped copy catches `i g n o r e`. But `dev_mode` (`(developer|god|unrestricted)\s*mode`) run on whitespace-free text matches "developer modeling" or "game developer models" as `developermode`. This is an app for developers, so such phrases will occur. Anchor the compact variants with a word-boundary check against the original text, or apply compact matching only to the highest-risk patterns. Then add a dozen benign engineering phrases to the control set.

- **Spend caps are soft.** Persisting per-user and global caps in `usage_events`, and checking them before the classifier call, is the right design. But the check happens before a call and spend is recorded after it, so the Prompt Lab's parallel five-technique plus judge runs can overshoot. With `ALLOWED_EMAILS="*"`, a few throwaway Google accounts can also exhaust the $20 global cap and deny service to everyone. Reserve an estimated cost before dispatch, and add a lower cap for accounts under 24 hours old or a per-IP rate limit.

- **Self-written guard test set.** The 30/31 result comes from 31 inputs written by the same developer who wrote the classifier prompt, with only 5 benign controls. Six semantic attacks all blocked tells you little about unseen phrasing, and it says nothing about the false-positive rate on real JDs and answers. Add a held-out set from a public injection corpus plus 50–100 real-looking answers and JDs, and report both block rate and false-positive rate.

## Prompt engineering

- **Rubric without ground truth.** `04_role_rubric.md` is the best prompt in the set: 1/3/5 anchors per dimension, an explicit "empty or off-topic answer scores 1 everywhere", and a data-not-instructions line. But every result in the README only shows ordering (weak < mid < strong), and nothing is compared with a human score. Calibration claims like "few-shot pulls the scale up" can't be verified. Add 10–15 answers with human-assigned scores and report agreement (MAE or Cohen's kappa) per technique.

- **Winner from tiny evidence.** "Winner: role + rubric" rests on 4.67 vs 4.33 on three answers to one question, one judge, one run each. With integer judge scores that is a single point on one item. The temperature decision likewise rests on two runs per setting. The caveats are stated honestly, but the prompt is still made the default on this evidence. Run at least 3 repeats per cell across 5+ questions, and report spread so differences smaller than the noise aren't presented as wins.

- **Judge ceiling and length bias.** Every judge score in both tables is 4 or 5, so the judge barely discriminates between techniques. `judge_feedback.md` also says "Prefer shorter feedback over longer feedback when both say the same thing", which tilts the concise-vs-detailed sweep toward concise before any data comes in. Make the criteria harsher or compare pairs (A vs B, order swapped), and drop the length preference when judging style. Then the claim "judge rates it as well or better" will mean something.

- **Examples contradict the rules.** `question_generation.md` says "Ask only one thing" and "Keep it short", and that senior questions are "still in one sentence". Its GOOD examples include "Tell me about a time you disagreed with a teammate. How did you resolve it?" and "Your web page loads slowly. What are the first three things you would check?", which are two sentences each. Models imitate examples over rules, so expect two-part questions. Rewrite those examples as single sentences, and add the missing question types to the "one per type" JSON examples (only 3 are shown).

- **Hidden thinking with no place to go.** `resume_tailor.md` has "Phase 1, think before you write (do not output this)" but its output is schema-bound JSON, so there is no scratch field and the phase is probably a no-op. Your own README found that asking for explicit reasoning trips Anthropic's filter, while a structured `analysis` field works. Add an optional `analysis` or `requirements_map` field before the bullets and drop it before export, or enable the provider's native reasoning parameter.

- **Appended blocks may clash.** `build_system_prompt` appends persona and style blocks after the task prompt, which keeps the Lab's variants clean. For coaching, though, `coach_guided.md` demands "exactly these four sections" and "Maximum 180 words", while a detailed-style block presumably asks for more. Later instructions usually win, so detailed coaching may break the constraints, and the sweep only tested feedback. Test persona and style crossed with the coach prompt and assert section count and word length in a unit test.

## Top 5 changes to make first

1. Escape closing delimiters in user text, guard `topics` and JD-derived questions, and move `role` out of the system prompt to close the second-order injection paths — **medium**.
2. Apply HTML and secret sanitization to structured outputs (`GuardPipeline.structured`) and buffer the coaching stream before display — **medium**.
3. Fix the compact-scan false positives (`dev_mode` first), add real-world benign controls and a held-out attack set, and make block messages say what to change — **small**.
4. Build a human-scored gold set, rerun the techniques and style sweep with repeats and a harsher or pairwise judge, and only then crown a default — **large**.
5. Rewrite the `question_generation.md` GOOD examples to be single-sentence, one-question items, and default mock mode to concise feedback — **small**.

## What we changed (2026-11-05)

Read as a reviewer's list, not an oracle: two findings were wrong about the code, the rest are
fair. Decisions below; the open items are tracked in PLAN.md.

**Done the same day**

- README opener rewritten to name the three user-facing features and separate the course
  deliverables (Usability 1).
- Mock sessions now default to concise feedback; guided sessions keep detailed (Usability 2,
  Top 5 #5).
- The leak block now logs "system prompt line N" instead of the first 40 characters of the
  leaked line, so the sidebar log and `security_events` no longer quote the prompt (Security 2).
- The README architecture diagram states that structured JSON calls get the leak check only,
  which is what the code does; the general claim was wider than the implementation (Security 1).

**Agreed, scheduled after the review**

- Escape closing delimiters (`</candidate_answer>`) in user text and run JD-derived questions
  and `topics` through `check_input` before they become "app-authored" context (Security 3,
  Top 5 #1). Real second-order path; medium effort.
- Sanitise the string fields of validated structured outputs with the same HTML/secret scrub
  (Security 1, Top 5 #2).
- Anchor the compact-scan variants with a word-boundary check so `developer modeling` is not
  `developermode`, and add benign engineering phrases to the control set (Security 4, Top 5 #3).
- Plain-language block messages per rule label (Usability 3).
- A human-scored gold set and repeated runs before any technique is called the winner (Prompt
  engineering 1-2, Top 5 #4). Large; the README caveats stay until then.
- Cross the persona and style blocks with the coach prompt in a test that asserts the four
  sections and the word cap (Prompt engineering 5).

**Rejected or corrected**

- "Stream check runs after every delta has been yielded, so a leak is already on screen": true,
  and by design. The coaching stream is capped at 180 words; the page replaces the displayed
  text on `GuardBlocked` (documented in CLAUDE.md). Buffering would remove the only streamed
  moment in the app for a leak class the leak check rarely catches anyway.
- "`role` is rendered into the system prompt without a re-check": the role comes from the
  preset list or from `check_input(..., InputKind.TITLE)` in the setup flow, and the resume and
  JD paths check titles the same way. Noted, no change.
- "The judge's length preference tilts the style sweep": the preference applies only "when
  both say the same thing"; the sweep's finding is that concise and detailed say the same
  thing. Kept, with the caveat added to the README sweep section.
- Rewriting the `question_generation.md` GOOD examples: a fair catch, left to the prompt's
  owner (the examples were tuned by hand in commit 869fd9b).
- Reserve-then-record spend accounting and per-IP limits: the global cap plus the OpenRouter
  key limit already bound the worst day; parallel overshoot is at most one Lab run (~$0.30).
