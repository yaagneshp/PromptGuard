import os
import secrets
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "change-me-dashboard-password")

SESSION_TIMEOUT_SECONDS = 30 * 60  # 30 minutes idle
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30


def require_password() -> None:
    """Simple session-scoped password gate. The dashboard shows aggregated
    audit data (per-user risk breakdowns, timestamps, platforms) - not raw
    PII, but still sensitive enough to not leave wide open to anyone who can
    reach the port. Includes a basic failed-attempt lockout (this is a
    single-shared-password MVP gate, not a hardened login system - a
    determined attacker with unlimited time could still wait out the 30s
    cooldown repeatedly) and an idle session timeout.
    """
    if st.session_state.get("authenticated"):
        authenticated_at = st.session_state.get("authenticated_at", 0)
        if time.time() - authenticated_at > SESSION_TIMEOUT_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state.pop("authenticated_at", None)
        else:
            return

    st.title("PromptGuard Dashboard")

    failed_attempts = st.session_state.get("failed_attempts", 0)
    locked_until = st.session_state.get("locked_until", 0)
    now = time.time()

    if now < locked_until:
        st.error(f"Too many failed attempts. Try again in {int(locked_until - now)}s.")
        st.stop()

    password = st.text_input("Password", type="password")
    if st.button("Sign in"):
        if secrets.compare_digest(password, DASHBOARD_PASSWORD):
            st.session_state["authenticated"] = True
            st.session_state["authenticated_at"] = now
            st.session_state["failed_attempts"] = 0
            st.rerun()
        else:
            failed_attempts += 1
            st.session_state["failed_attempts"] = failed_attempts
            if failed_attempts >= MAX_FAILED_ATTEMPTS:
                st.session_state["locked_until"] = now + LOCKOUT_SECONDS
                st.session_state["failed_attempts"] = 0
                st.error(f"Too many failed attempts. Try again in {LOCKOUT_SECONDS}s.")
            else:
                st.error("Incorrect password.")

    st.stop()
