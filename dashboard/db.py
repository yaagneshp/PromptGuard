import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "promptguard.db"


def get_connection() -> sqlite3.Connection:
    # Read-only URI connection: the dashboard must never write to the
    # backend's live database, and this avoids lock contention with the
    # backend's own write connections while it's running.
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def load_events() -> pd.DataFrame:
    query = """
    SELECT
        e.id AS event_id,
        u.external_user_id,
        p.name AS platform,
        e.redacted_text,
        e.char_count,
        e.occurred_at,
        e.received_at,
        r.regex_score,
        r.presidio_score,
        r.contextual_score,
        r.combined_score,
        r.risk_level,
        r.policy_violation
    FROM events e
    JOIN users u ON u.id = e.user_id
    JOIN platforms p ON p.id = e.platform_id
    JOIN risk_scores r ON r.event_id = e.id
    ORDER BY e.received_at DESC
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, parse_dates=["occurred_at", "received_at"])


def load_detections() -> pd.DataFrame:
    query = "SELECT event_id, category, match_count, detector_source FROM detections"
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


def load_compliance_tags() -> pd.DataFrame:
    query = "SELECT event_id, category, gdpr_article, rationale FROM compliance_tags"
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)
