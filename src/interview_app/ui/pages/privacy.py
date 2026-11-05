"""Privacy policy: a public page (no sign-in) that the Google consent screen links to."""

from __future__ import annotations

import streamlit as st

from interview_app.config import get_settings
from interview_app.ui.theme import APP_NAME

LAST_UPDATED = "5 November 2026"

_POLICY = """
**Last updated: {updated}**

{app} is a personal AI interview coach built by Sonali Hirave as a learning project. This page
explains what the app stores when you use it and who else processes that data.

### What we collect

- **Your Google account identity.** When you sign in with Google we receive your email address,
  display name and profile picture. The email address is the key under which your data is stored;
  the name and picture are only shown in the sidebar while you are signed in.
- **What you type.** Interview answers, pasted job descriptions and any other text you enter.
- **What the app generates for you.** Questions, scores, feedback, prep plans and session summaries.
- **Security and usage records.** Each request is checked by a security guard; its decision
  (allowed, redacted or blocked), the matched rule and a short reason are logged, together with
  the model used, token counts and cost, so that daily spending limits can be enforced.

We do not collect payment details, location, contacts or anything from your Google account
beyond the basic profile above.

### Who processes it

- **Google** handles sign-in. We never see your password.
- **OpenRouter** and the model providers it routes to (Anthropic, OpenAI, Google) receive the
  text you type, the questions and your answers, in order to generate feedback. These requests
  are sent under OpenRouter's privacy terms; the app does not opt in to training on your data.
- **Neon** (PostgreSQL, EU Frankfurt region) stores your sessions and the records above.
- **Streamlit Community Cloud** hosts the app and keeps its server logs.

Your data is not sold, shared with advertisers or used for any purpose other than running the
coaching features for you.

### Cookies

The app sets a signed sign-in cookie so that you stay signed in, plus the technical cookies
Streamlit needs to run a session. There are no advertising or tracking cookies set by the app.

### Retention and deletion

Sessions and records are kept so that you can revisit your history. To have everything stored
under your email address deleted, email **{contact}** from that address and it will be removed.

### Contact

Questions about this policy: **{contact}**.
"""


def render() -> None:
    _, col, _ = st.columns([1, 3, 1])
    with col:
        st.title(f"🔒 {APP_NAME} privacy policy")
        st.markdown(
            _POLICY.format(
                app=APP_NAME, updated=LAST_UPDATED, contact=get_settings().privacy_contact_email
            )
        )
        st.page_link(st.session_state.pages["home"], label="← Back to Hoot", icon="🦉")
