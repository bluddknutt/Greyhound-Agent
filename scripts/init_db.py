"""
Initialise the Greyhound Agent SQLite database.

Creates three tables if they do not already exist:
  predictions  — one row per dog picked per race run
  results      — actual race outcomes fetched that evening
  pnl_log      — daily profit/loss summary

Run directly:
  python3 scripts/init_db.py
Or imported from other helper scripts.
"""

import os
import sqlite3
import sys

# Allow running from any working directory
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "data", "greyhound.db")


def get_db_path() -> str:
    # Respect DB_PATH env var (set in .env) or fall back to default
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    return os.environ.get("DB_PATH", DEFAULT_DB)


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            race_date   TEXT    NOT NULL,
            track       TEXT    NOT NULL,
            race_number INTEGER NOT NULL,
            box         INTEGER,
            dog_name    TEXT    NOT NULL,
            final_score REAL,
            bet_type    TEXT    DEFAULT 'win',   -- 'win' or 'place'
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE(race_date, track, race_number, box)
        );

        CREATE TABLE IF NOT EXISTS results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            race_date       TEXT    NOT NULL,
            track           TEXT    NOT NULL,
            race_number     INTEGER NOT NULL,
            box             INTEGER,
            dog_name        TEXT    NOT NULL,
            finish_position INTEGER,
            win_time        REAL,
            created_at      TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE(race_date, track, race_number, box)
        );

        CREATE TABLE IF NOT EXISTS pnl_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            race_date    TEXT NOT NULL UNIQUE,
            total_picks  INTEGER DEFAULT 0,
            wins         INTEGER DEFAULT 0,
            places       INTEGER DEFAULT 0,  -- finished 2nd or 3rd
            profit_loss  REAL    DEFAULT 0.0,
            logged_at    TEXT    DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    return conn


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    conn = init_db(db_path)
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    print(f"Database initialised: {path}")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (t,) in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count} rows")
    conn.close()
