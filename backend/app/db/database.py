"""
Minimal SQLite persistence for scan history. Uses stdlib sqlite3 directly —
no ORM needed for a single table at this scale.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    subject TEXT,
    sender TEXT,
    claimed_brand TEXT,
    is_brand_verified INTEGER,
    risk_score INTEGER,
    verdict TEXT,
    breakdown_json TEXT,
    social_engineering_json TEXT,
    suspicious_evidence_json TEXT,
    explanation TEXT,
    actionable_advice_json TEXT,
    source TEXT,
    body TEXT,
    user_feedback TEXT
);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _lock, get_connection() as conn:
        conn.execute(_SCHEMA)
        # Migration for DBs created before the `body` column existed.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(scan_results)")}
        if "body" not in existing_cols:
            conn.execute("ALTER TABLE scan_results ADD COLUMN body TEXT")
        if "user_feedback" not in existing_cols:
            conn.execute("ALTER TABLE scan_results ADD COLUMN user_feedback TEXT")
        conn.commit()


def save_scan_result(data: dict, source: str = "manual") -> int:
    with _lock, get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO scan_results (
                timestamp, subject, sender, claimed_brand, is_brand_verified,
                risk_score, verdict, breakdown_json, social_engineering_json,
                suspicious_evidence_json, explanation, actionable_advice_json, source, body
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                data.get("subject", ""),
                data.get("sender", ""),
                data.get("claimed_brand"),
                int(bool(data.get("is_brand_verified"))),
                data.get("risk_score", 0),
                data.get("verdict", "SAFE"),
                json.dumps(data.get("breakdown", {})),
                json.dumps(data.get("social_engineering", [])),
                json.dumps(data.get("suspicious_evidence", [])),
                data.get("explanation", ""),
                json.dumps(data.get("actionable_advice", [])),
                source,
                data.get("body", ""),
            ),
        )
        conn.commit()
        return cur.lastrowid


def set_user_feedback(scan_id: int, feedback: str) -> bool:
    """feedback: 'spam' or 'valid' — the user's own verdict from the extension
    popup or the dashboard, stored alongside PhishMind's own score so the two
    can be compared later (a simple feedback loop, not used to retrain anything
    in this MVP)."""
    with _lock, get_connection() as conn:
        cur = conn.execute(
            "UPDATE scan_results SET user_feedback = ? WHERE id = ?", (feedback, scan_id)
        )
        conn.commit()
        return cur.rowcount > 0


def get_scan_by_id(scan_id: int) -> dict | None:
    with _lock, get_connection() as conn:
        row = conn.execute("SELECT * FROM scan_results WHERE id = ?", (scan_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_history(limit: int = 50) -> list[dict]:
    with _lock, get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scan_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "timestamp": row["timestamp"],
        "subject": row["subject"],
        "sender": row["sender"],
        "claimed_brand": row["claimed_brand"],
        "is_brand_verified": bool(row["is_brand_verified"]),
        "risk_score": row["risk_score"],
        "verdict": row["verdict"],
        "breakdown": json.loads(row["breakdown_json"] or "{}"),
        "social_engineering": json.loads(row["social_engineering_json"] or "[]"),
        "suspicious_evidence": json.loads(row["suspicious_evidence_json"] or "[]"),
        "explanation": row["explanation"],
        "actionable_advice": json.loads(row["actionable_advice_json"] or "[]"),
        "source": row["source"],
        "body": row["body"] if "body" in row.keys() else "",
        "user_feedback": row["user_feedback"] if "user_feedback" in row.keys() else None,
    }
