"""Privacy policy: a public page (no sign-in) that the Google consent screen links to."""

from __future__ import annotations

import streamlit as st

from interview_app.ui.theme import APP_NAME

LAST_UPDATED = "5 November 2026"
PROJECT_URL = "https://github.com/hiravesonali/Interview-prep-app"

_POLICY = """
**Last updated: {updated}**

{app} is a personal side project for practising technical interviews with an AI coach. It is
not a commercial service.

### What is stored

- Your Google account email, name and profile picture, used only to sign you in and keep your
  sessions separate from other users'.
- The text you enter (answers, job descriptions) and the questions, scores and feedback
  generated for you, so that you can revisit past sessions.
- Resumes you upload or paste: the extracted text and the parsed sections, plus the tailored
  versions built from them. The uploaded file itself is not kept. You can delete any resume
  from the AI resume builder page at any time.
- Basic usage records needed to keep the project's AI spending within its limits.

### How it is used

- Your text is sent to third-party AI models to generate questions, feedback and tailored
  resumes. Email addresses and phone numbers are removed before sending. It is not used for
  advertising, sold, or shared for any other purpose.
- The app sets only the cookies needed to keep you signed in. There are no advertising or
  tracking cookies.

### Your choices

- You can sign out at any time.
- To have your data deleted, open an issue on the [project page]({project}).
"""


def render() -> None:
    _, col, _ = st.columns([1, 3, 1])
    with col:
        st.title(f"🔒 {APP_NAME} privacy policy")
        st.markdown(_POLICY.format(app=APP_NAME, updated=LAST_UPDATED, project=PROJECT_URL))
        st.page_link(st.session_state.pages["home"], label="← Back to Hoot", icon="🦉")
