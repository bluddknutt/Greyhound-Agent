"""SQLite-backed persistence for pipeline runs and bet tracking."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "runs.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or _DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_date TEXT NOT NULL,
                source TEXT NOT NULL,
                venue_filter TEXT,
                dry_run INTEGER NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                summary_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                venue TEXT,
                race_number INTEGER,
                box INTEGER,
                dog_name TEXT,
                model_prob REAL,
                odds REAL,
                overlay_pct REAL,
                stake REAL,
                outcome TEXT DEFAULT 'pending',
                return_amount REAL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
            """
        )


def record_run(result: dict[str, Any] | None, *, status: str, error: str | None = None, db_path: str | None = None) -> int:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    run_date = (result or {}).get("run_date", "")
    source = (result or {}).get("source", "")
    venue_filter = (result or {}).get("venue_filter")
    dry_run = 1 if (result or {}).get("dry_run") else 0
    summary = (result or {}).get("summary", {})

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (created_at, run_date, source, venue_filter, dry_run, status, error, summary_json, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                run_date,
                source,
                venue_filter,
                dry_run,
                status,
                error,
                json.dumps(summary),
                json.dumps(result or {}),
            ),
        )
        run_id = cursor.lastrowid

        for bet in (result or {}).get("selected_bets", []):
            conn.execute(
                """
                INSERT INTO bets (run_id, venue, race_number, box, dog_name, model_prob, odds, overlay_pct, stake)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    bet.get("venue"),
                    bet.get("race_number"),
                    bet.get("box"),
                    bet.get("dog_name"),
                    bet.get("model_prob"),
                    bet.get("odds"),
                    bet.get("overlay_pct"),
                    bet.get("bet_amount"),
                ),
            )

    return int(run_id)


def fetch_latest_run(db_path: str | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload["run_id"] = row["id"]
    payload["status"] = row["status"]
    payload["error"] = row["error"]
    payload["created_at"] = row["created_at"]
    return payload


def fetch_run_history(limit: int = 25, db_path: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    history = []
    for row in rows:
        history.append(
            {
                "run_id": row["id"],
                "created_at": row["created_at"],
                "run_date": row["run_date"],
                "source": row["source"],
                "venue_filter": row["venue_filter"],
                "dry_run": bool(row["dry_run"]),
                "status": row["status"],
                "error": row["error"],
                "summary": json.loads(row["summary_json"]),
            }
        )
    return history


def fetch_races_for_date(run_date: str, db_path: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT payload_json FROM runs WHERE run_date = ? AND status = 'success' ORDER BY id DESC",
            (run_date,),
        ).fetchall()
    if not rows:
        return []

    latest_payload = json.loads(rows[0]["payload_json"])
    return latest_payload.get("predictions", [])


def performance_summary(db_path: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT stake, outcome, return_amount FROM bets").fetchall()

    total_bets = len(rows)
    if total_bets == 0:
        return {"total_bets": 0, "strike_rate": 0.0, "roi": 0.0, "profit_loss": 0.0}

    total_stake = sum(float(row["stake"] or 0.0) for row in rows)
    total_return = sum(float(row["return_amount"] or 0.0) for row in rows)
    wins = sum(1 for row in rows if row["outcome"] == "win")
    profit_loss = total_return - total_stake
    roi = (profit_loss / total_stake) if total_stake else 0.0
    return {
        "total_bets": total_bets,
        "strike_rate": wins / total_bets,
        "roi": roi,
        "profit_loss": profit_loss,
    }
