"""Sign-in gate (Streamlit's built-in OIDC login, Google by default) and production mode.

Why: in production the OpenRouter key lives in server secrets, so an open URL would let anyone
spend it. The gate is active when `APP_ENV=prod` or whenever an `[auth]` block exists in
`.streamlit/secrets.toml` (so the flow can be tried locally). Without either, the app runs as
the single local user, exactly as in Sprint 1.
"""

from __future__ import annotations

import html
import os

import streamlit as st

from interview_app.config import Settings
from interview_app.storage.store import LOCAL_USER
from interview_app.ui.theme import APP_NAME, APP_TAGLINE, mascot


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
    """Pure allowlist check. An empty allowlist admits nobody: the gate fails closed."""
    return bool(email) and email.strip().lower() in allowlist


def signed_in_email() -> str | None:
    user = st.user
    return user.get("email") if user.get("is_logged_in") else None


def current_user_id() -> str:
    """Storage scope: the signed-in email, or `local` when running without sign-in."""
    return signed_in_email() or LOCAL_USER


def require_login(settings: Settings) -> None:
    """Stop the script run until an allowed user is signed in. No-op in local mode."""
    if not auth_configured():
        if settings.is_prod:
            st.error("APP_ENV=prod but no [auth] block in secrets.toml: refusing to run open.")
            st.stop()
        return
    if not st.user.get("is_logged_in"):
        _sign_in_screen()
        st.stop()
    if not is_allowed(st.user.get("email"), settings.allowed_email_set):
        st.warning(
            f"{html.escape(st.user.get('email') or 'This account')} is not on the allowlist "
            "for this Hoot instance."
        )
        if st.button("Sign out"):
            st.logout()
        st.stop()


def _sign_in_screen() -> None:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.html(
            f'<div class="hoot-signin">{mascot(96)}<div class="name">{APP_NAME}</div>'
            f'<div class="tag">{APP_TAGLINE}</div>'
            "<p>Your personal AI interview coach. Sign in to continue.</p></div>"
        )
        if st.button("Sign in with Google", type="primary", width="stretch"):
            st.login()
