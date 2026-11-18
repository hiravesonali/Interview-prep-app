"""Sign-in gate (Streamlit's built-in OIDC login, Google by default) and production mode.

Why: in production the OpenRouter key lives in server secrets, so an open URL would let anyone
spend it. The gate is active when `APP_ENV=prod` or whenever an `[auth]` block exists in
`.streamlit/secrets.toml` (so the flow can be tried locally). Without either, the app runs as
the single local user, exactly as in Sprint 1.

Guest demo (`GUEST_MODE_ENABLED`): the sign-in card also offers "Try as guest". A guest gets a
random `guest-…` user id for this browser session only, so guests never see each other's data;
their spend shares one daily cap and their data is purged after 24 h (PLAN.md §12).
"""

from __future__ import annotations

import html
import os
import secrets

import streamlit as st
from streamlit.navigation.page import StreamlitPage

from interview_app.config import Settings
from interview_app.storage.store import GUEST_PREFIX, LOCAL_USER
from interview_app.ui.theme import APP_NAME, APP_TAGLINE, mascot

_GUEST_KEY = "guest_id"  # st.session_state key; lives as long as the browser session


def export_secrets_to_env() -> None:
    """Make top-level `secrets.toml` values visible to pydantic-settings as env vars.

    Streamlit Community Cloud stores configuration in secrets, not in a `.env` file; this keeps
    `config.Settings` the single way settings are read. Existing env vars win.
    """
    try:
        items = list(st.secrets.items())
    except Exception:  # no secrets file: nothing to export  # noqa: BLE001
        return
    for key, value in items:
        if isinstance(value, str | int | float | bool):
            os.environ.setdefault(key.upper(), str(value))


def auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:  # noqa: BLE001
        return False


def is_allowed(email: str | None, allowlist: frozenset[str]) -> bool:
    """Pure allowlist check: `"*"` admits any signed-in account, an empty list admits nobody."""
    if not email:
        return False
    return "*" in allowlist or email.strip().lower() in allowlist


def signed_in_email() -> str | None:
    user = st.user
    return user.get("email") if user.get("is_logged_in") else None


def guest_id() -> str | None:
    """The guest user id of this browser session, if the visitor chose "Try as guest"."""
    return st.session_state.get(_GUEST_KEY)


def is_guest() -> bool:
    return guest_id() is not None and signed_in_email() is None


def new_guest_id() -> str:
    """Random, unguessable, one per browser session: guests never share or reach others' data."""
    return f"{GUEST_PREFIX}{secrets.token_hex(8)}"


def current_user_id() -> str:
    """Storage scope: the signed-in email, a guest id, or `local` when running without sign-in."""
    return signed_in_email() or guest_id() or LOCAL_USER


def require_login(settings: Settings, privacy_page: StreamlitPage | None = None) -> None:
    """Stop the script run until an allowed user or a guest is in. No-op in local mode.

    `privacy_page` is linked from the sign-in card so the policy is reachable before sign-in.
    """
    if not auth_configured():
        if settings.is_prod:
            st.error("APP_ENV=prod but no [auth] block in secrets.toml: refusing to run open.")
            st.stop()
        return
    if not st.user.get("is_logged_in"):
        if settings.guest_mode_enabled and guest_id():
            return
        _sign_in_screen(privacy_page, guest_allowed=settings.guest_mode_enabled)
        st.stop()
    if not is_allowed(st.user.get("email"), settings.allowed_email_set):
        st.warning(
            f"{html.escape(st.user.get('email') or 'This account')} is not on the allowlist "
            "for this Hoot instance."
        )
        if st.button("Sign out"):
            st.logout()
        st.stop()


def _sign_in_screen(privacy_page: StreamlitPage | None, *, guest_allowed: bool) -> None:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.html(
            f'<div class="hoot-signin">{mascot(96)}<div class="name">{APP_NAME}</div>'
            f'<div class="tag">{APP_TAGLINE}</div>'
            "<p>Your personal AI interview coach. Sign in to continue.</p></div>"
        )
        if st.button("Sign in with Google", type="primary", width="stretch"):
            st.login()
        if guest_allowed:
            if st.button("Try as guest (no account)", width="stretch"):
                st.session_state[_GUEST_KEY] = new_guest_id()
                st.rerun()
            st.caption(
                "Full app, no sign-in. Your work lasts until you refresh or close the tab "
                "and is deleted from the server within 24 hours."
            )
        if privacy_page is not None:
            st.page_link(privacy_page, label="Privacy policy", icon="🔒")
