---
name: defense-prep
description: Prepare Sonali to defend the Hoot project in her Turing College Sprint 1 review. Use this whenever she asks to practise for the review, rehearse, "explain this decision", "why did we choose X", wants likely reviewer questions, a mock review, or a short spoken explanation of any part of the app (guard pipeline, models, structured outputs, prompt techniques, judge, temperature, cost tracking, Streamlit state). Also use it when she asks "what should I be able to explain" or "what will the reviewer ask". The deliverable is an answer in her voice that she can say out loud, not documentation.
---

# Defense prep: own every decision

The review is a conversation, not a demo. The reviewer will pick a part of the app and ask why
it is built that way, what else was considered, and what would break. Sonali has to answer in
her own words, so the job here is to turn the written record into short spoken answers and to
rehearse them, not to produce more documents.

## Sources, in order of authority

1. `PLAN.md` sections 6 (Decisions), 3 (Architecture, Key tech decisions), 8 (gap closure): what
   was decided and why. If a decision is not recorded there, say so rather than inventing a
   rationale.
2. `README.md`: Security design, Jailbreak experiment, Prompt engineering, Results, Tuning one
   setting. Every number in an answer comes from here or from `data/prompt_lab.json`; never
   quote a figure from memory.
3. `CLAUDE.md` Architecture paragraph for the mechanics (choke point, overrides, structured
   output repair retry, ASCII header incident).
4. The code itself when the question is "how exactly": read the function before describing it.

Read the learning profile skill too: she is a senior JS/TS developer new to Python, so Python
idioms (pydantic models, `functools.cache`, generators for streaming) are fair questions.

## Decisions she must be able to defend

Each of these is one spoken answer of about two minutes. Prepare them on request, one at a time:

- Why every LLM call goes through one guard pipeline; why features never touch the client.
- Three guard layers (rules, Haiku classifier, output guard) and why the classifier fails open.
- Why `{input}` is the only thing substituted in user templates (prompt injection through
  app-authored context, braces in JSON).
- Model choice: Sonnet 5.5 main, Haiku 4.5 guard, why not Haiku 5.5 (allowlist), course list.
- Structured outputs: pydantic schema via `response_format`, one repair retry, why `length`
  and `content_filter` raise immediately.
- Cost accounting from OpenRouter's `usage.cost`, why it is per browser session.
- Five prompt techniques, what each changes in the prompt, why role + rubric is the default
  grader, what the judge measures and why it is a different model family.
- Temperature: 0.2 for scoring, 0.5 for coaching, what the sweep showed.
- Jailbreak experiment: what was tried, what got through, what the Excel sheet records.
- Why the Prompt Lab is a developer tool and not in the user menu.
- Streamlit state: one pipeline per browser session, why pages are `render()` functions, why
  stream output can be replaced after the output guard.
- What was deliberately deferred (RAG, LangChain, deployment) and what she would do next.

## Answer format

Write each answer as she would say it: first person, plain sentences, no bullet lists, no code,
roughly 150-250 words. Follow this arc without labelling the parts:

context (what problem this part solves) → the choice → the one or two alternatives considered
and why they lost → the trade-off she accepted → what she would change with more time.

After the answer, list three follow-up questions a reviewer is likely to ask, each with a
one-sentence pointer to where the answer lives (file or README section), not the full answer.
The pointer is enough: she should find and phrase the follow-up herself.

Keep the voice hers. She chose Sonnet 5.5, she wrote and tuned prompts 02-05, she approved the
guard design; say "I" for those. For things Claude scaffolded, the honest phrasing is "I had
the scaffold generated and reviewed it; the decision was mine because ...". A reviewer who
hears a memorised explanation of code the student does not own will dig until it shows.

## Mock review mode

When she asks for a mock review, act as the Turing College reviewer:

- Ask one question at a time and wait for her answer. Do not answer for her.
- Start broad ("walk me through what happens when I submit an answer"), then follow the thread
  into one specific decision, then ask what would break if she removed it.
- After her answer, give two lines of feedback: what was convincing, what was vague or wrong
  (with the file to re-read). Then the next question.
- Mix in one Python question per session (why pydantic over dicts, what `functools.cache` does
  to `get_settings()`, what a generator buys the streaming call).
- End with a short list of the questions she stumbled on, so she can rehearse those first.

## Things not to do

- Do not rewrite PLAN.md or README during prep. If prep uncovers a gap in the record, say so
  and let her decide whether to add it.
- Do not produce slides or a long document unless asked; the output is spoken answers.
- Do not invent numbers, dates or test counts. Check the file, or say the number is not recorded.
