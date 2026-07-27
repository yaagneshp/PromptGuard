import os
import secrets
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "change-me-dashboard-password")


def require_password() -> None:
    """Simple session-scoped password gate. The dashboard shows aggregated
    audit data (per-user risk breakdowns, timestamps, platforms) - not raw
    PII, but still sensitive enough to not leave wide open to anyone who can
    reach the port."""
    if st.session_state.get("authenticated"):
        return

    st.title("PromptGuard Dashboard")
    password = st.text_input("Password", type="password")
    if st.button("Sign in"):
        if secrets.compare_digest(password, DASHBOARD_PASSWORD):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()
