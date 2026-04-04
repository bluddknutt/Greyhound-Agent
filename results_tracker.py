"""
Results tracking module — stores predictions and actual outcomes in SQLite.

Schema: predictions table with one row per dog per race (top 3).
Use log_prediction() after generating picks, update_result() after races run,
and get_summary() for P&L analytics.
"""

import sqlite3
import os
from datetime import date as date_type, datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "results.db")


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(db_path: str = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                race_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting         TEXT    NOT NULL,
                race_number     INTEGER NOT NULL,
                date            TEXT    NOT NULL,
                dog_name        TEXT    NOT NULL,
                predicted_rank  INTEGER NOT NULL,
                actual_result   INTEGER,
                odds_at_prediction REAL,
                stake           REAL    NOT NULL DEFAULT 10.0,
                profit_loss     REAL,
                confidence_tier TEXT    NOT NULL DEFAULT 'medium',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE (meeting, race_number, date, dog_name)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_meeting_race_date
            ON predictions (meeting, race_number, date)
        """)
        conn.commit()


def log_prediction(
    meeting: str,
    race_number: int,
    date: str,
    dog_name: str,
    predicted_rank: int,
    odds_at_prediction: Optional[float] = None,
    stake: float = 10.0,
    confidence_tier: str = "medium",
    db_path: str = DB_PATH,
) -> int:
    """
    Insert a new prediction row. Returns the new race_id.

    Parameters
    ----------
    meeting         : venue/track name (e.g. "Sandown Park")
    race_number     : race number on the card
    date            : ISO date string "YYYY-MM-DD"
    dog_name        : name of the predicted dog
    predicted_rank  : 1 = top pick, 2 = second, 3 = third
    odds_at_prediction : decimal odds at time of prediction (e.g. 3.50)
    stake           : amount wagered (default $10)
    confidence_tier : "high" | "medium" | "low"
    """
    _init_db(db_path)
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO predictions
                (meeting, race_number, date, dog_name, predicted_rank,
                 odds_at_prediction, stake, confidence_tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (meeting, race_number, date, dog_name, predicted_rank,
             odds_at_prediction, stake, confidence_tier),
        )
        conn.commit()
        # Return existing race_id if the row was already present (IGNORE fired)
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT race_id FROM predictions WHERE meeting=? AND race_number=? AND date=? AND dog_name=?",
            (meeting, race_number, date, dog_name),
        ).fetchone()
        return row["race_id"] if row else None


def update_result(
    race_id: int,
    actual_result: int,
    profit_loss: Optional[float] = None,
    db_path: str = DB_PATH,
) -> None:
    """
    Set the actual finishing position for a logged prediction and compute P&L.

    If profit_loss is None it is calculated automatically:
      - Win bet on rank-1 pick wins if actual_result == 1
        profit = stake * (odds - 1)
      - Place bet on rank-2/3 picks wins if actual_result <= 3
        profit = stake * (odds / 4 - 1)   (rough each-way approx)
      - Otherwise profit = -stake

    Parameters
    ----------
    race_id       : primary key from predictions table
    actual_result : actual finishing position (1 = winner)
    profit_loss   : override calculated P&L if provided
    """
    _init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT predicted_rank, odds_at_prediction, stake FROM predictions WHERE race_id = ?",
            (race_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"No prediction found with race_id={race_id}")

        if profit_loss is None:
            odds = row["odds_at_prediction"] or 0.0
            stake = row["stake"]
            rank = row["predicted_rank"]
            if rank == 1 and actual_result == 1:
                profit_loss = stake * (odds - 1)
            elif rank in (2, 3) and actual_result <= 3:
                place_odds = max(1.0, odds / 4.0)
                profit_loss = stake * (place_odds - 1)
            else:
                profit_loss = -stake

        conn.execute(
            "UPDATE predictions SET actual_result = ?, profit_loss = ? WHERE race_id = ?",
            (actual_result, profit_loss, race_id),
        )
        conn.commit()


def get_summary(db_path: str = DB_PATH) -> dict:
    """
    Return a dict with P&L analytics across all settled predictions.

    Keys
    ----
    total_bets      : total number of predictions logged
    settled_bets    : predictions with actual_result filled
    win_rate        : fraction of settled bets that were profitable
    roi_pct         : Return on Investment as a percentage
    total_profit_loss : net profit/loss across all settled bets
    total_staked    : sum of stakes on settled bets
    streak          : current consecutive win (+) or loss (-) streak
    by_confidence   : dict keyed by confidence_tier with sub-summary dicts
    """
    _init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT race_id, meeting, race_number, date, dog_name,
                   predicted_rank, actual_result, odds_at_prediction,
                   stake, profit_loss, confidence_tier
            FROM predictions
            ORDER BY created_at ASC
            """
        ).fetchall()

    total_bets = len(rows)
    settled = [r for r in rows if r["actual_result"] is not None]
    settled_bets = len(settled)
    wins = [r for r in settled if (r["profit_loss"] or 0) > 0]
    win_rate = len(wins) / settled_bets if settled_bets else 0.0
    total_profit_loss = sum(r["profit_loss"] or 0 for r in settled)
    total_staked = sum(r["stake"] for r in settled)
    roi_pct = (total_profit_loss / total_staked * 100) if total_staked > 0 else 0.0

    # Current streak — scan from most recent backwards
    streak = 0
    for r in reversed(settled):
        pl = r["profit_loss"] or 0
        if streak == 0:
            streak = 1 if pl > 0 else -1
        elif streak > 0 and pl > 0:
            streak += 1
        elif streak < 0 and pl <= 0:
            streak -= 1
        else:
            break

    # Breakdown by confidence tier
    tiers = {}
    for r in settled:
        tier = r["confidence_tier"] or "medium"
        if tier not in tiers:
            tiers[tier] = {"bets": 0, "wins": 0, "profit_loss": 0.0, "staked": 0.0}
        tiers[tier]["bets"] += 1
        if (r["profit_loss"] or 0) > 0:
            tiers[tier]["wins"] += 1
        tiers[tier]["profit_loss"] += r["profit_loss"] or 0
        tiers[tier]["staked"] += r["stake"]

    by_confidence = {}
    for tier, stats in tiers.items():
        by_confidence[tier] = {
            "bets": stats["bets"],
            "win_rate": stats["wins"] / stats["bets"] if stats["bets"] else 0.0,
            "roi_pct": (stats["profit_loss"] / stats["staked"] * 100) if stats["staked"] > 0 else 0.0,
            "profit_loss": stats["profit_loss"],
        }

    return {
        "total_bets": total_bets,
        "settled_bets": settled_bets,
        "win_rate": win_rate,
        "roi_pct": roi_pct,
        "total_profit_loss": total_profit_loss,
        "total_staked": total_staked,
        "streak": streak,
        "by_confidence": by_confidence,
    }


def get_pending(db_path: str = DB_PATH) -> list[dict]:
    """Return all predictions that have no actual_result yet."""
    _init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT race_id, meeting, race_number, date, dog_name,
                   predicted_rank, odds_at_prediction, stake, confidence_tier
            FROM predictions
            WHERE actual_result IS NULL
            ORDER BY date ASC, meeting ASC, race_number ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]
