"""
P&L Results Tracker — stores predictions and actual results in SQLite.

Database: data/results.db

Schema
------
predictions table:
  id               INTEGER PK
  race_id          TEXT        -- "{venue_slug}_{race_number}_{date}"  (unique per race)
  meeting          TEXT        -- "The Meadows"
  race_number      INTEGER
  date             TEXT        -- "YYYY-MM-DD"
  dog_name         TEXT
  box              INTEGER
  predicted_rank   INTEGER     -- 1..4
  confidence_tier  TEXT        -- "Tier 1".."Tier 4"
  composite_score  REAL
  win_prob         REAL
  odds_at_prediction REAL      -- implied_odds from scorer
  stake            REAL        -- default 10.0
  actual_result    INTEGER     -- finishing position; NULL until resolved
  profit_loss      REAL        -- NULL until resolved
  logged_at        TEXT        -- ISO timestamp

Unique constraint: (race_id, dog_name) — prevents double-logging the same runner.
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "results.db")
DEFAULT_STAKE = 10.0

AEST = timezone(timedelta(hours=11))


def _db_path():
    return os.environ.get("RESULTS_DB", DB_PATH)


def _connect():
    path = _db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id          TEXT NOT NULL,
            meeting          TEXT NOT NULL,
            race_number      INTEGER NOT NULL,
            date             TEXT NOT NULL,
            dog_name         TEXT NOT NULL,
            box              INTEGER,
            predicted_rank   INTEGER NOT NULL,
            confidence_tier  TEXT,
            composite_score  REAL,
            win_prob         REAL,
            odds_at_prediction REAL,
            stake            REAL NOT NULL DEFAULT 10.0,
            actual_result    INTEGER,
            profit_loss      REAL,
            logged_at        TEXT NOT NULL,
            UNIQUE(race_id, dog_name)
        )
    """)
    conn.commit()


def _make_race_id(meeting: str, race_number: int, date: str) -> str:
    slug = meeting.lower().replace(" ", "-").replace("_", "-")
    return f"{slug}_{race_number}_{date}"


def _confidence_tier(predicted_rank: int, win_prob: float) -> str:
    if predicted_rank == 1 and win_prob >= 0.30:
        return "Tier 1"
    if (predicted_rank == 1 and win_prob >= 0.20) or (predicted_rank == 2 and win_prob >= 0.25):
        return "Tier 2"
    if predicted_rank <= 2:
        return "Tier 3"
    return "Tier 4"


def log_prediction(
    meeting: str,
    race_number: int,
    date: str,
    dog_name: str,
    box: int,
    predicted_rank: int,
    composite_score: float,
    win_prob: float,
    odds_at_prediction: float,
    stake: float = DEFAULT_STAKE,
) -> int | None:
    """
    Insert a prediction row.  Returns the new row id, or None if already exists.

    Parameters
    ----------
    meeting            : venue name, e.g. "The Meadows"
    race_number        : integer race number on the card
    date               : "YYYY-MM-DD"
    dog_name           : runner name
    box                : box draw
    predicted_rank     : 1..4 from get_top4()
    composite_score    : raw composite value from scorer
    win_prob           : normalised win probability
    odds_at_prediction : implied_odds (1 / win_prob)
    stake              : dollars staked (default 10.0)
    """
    race_id = _make_race_id(meeting, race_number, date)
    tier = _confidence_tier(predicted_rank, win_prob)
    logged_at = datetime.now(AEST).isoformat()

    with _connect() as conn:
        _init_db(conn)
        try:
            cur = conn.execute(
                """
                INSERT INTO predictions
                    (race_id, meeting, race_number, date, dog_name, box,
                     predicted_rank, confidence_tier, composite_score, win_prob,
                     odds_at_prediction, stake, logged_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (race_id, meeting, race_number, date, dog_name, box,
                 predicted_rank, tier, composite_score, win_prob,
                 odds_at_prediction, stake, logged_at),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Already logged
            return None


def update_result(meeting: str, race_number: int, date: str, dog_name: str, actual_position: int):
    """
    Record the actual finishing position and calculate profit/loss.

    actual_position = 1 → win → profit = stake * (odds - 1)
    actual_position > 1 → loss → profit = -stake
    """
    race_id = _make_race_id(meeting, race_number, date)

    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            "SELECT id, stake, odds_at_prediction FROM predictions WHERE race_id=? AND dog_name=?",
            (race_id, dog_name),
        ).fetchone()

        if row is None:
            return False

        stake = row["stake"]
        odds = row["odds_at_prediction"] or 0.0
        profit_loss = stake * (odds - 1) if actual_position == 1 else -stake

        conn.execute(
            "UPDATE predictions SET actual_result=?, profit_loss=? WHERE id=?",
            (actual_position, round(profit_loss, 2), row["id"]),
        )
        conn.commit()
        return True


def get_pending(date: str | None = None):
    """
    Return all predictions where actual_result IS NULL.
    Optionally filter to a specific date.
    """
    with _connect() as conn:
        _init_db(conn)
        if date:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE actual_result IS NULL AND date=? ORDER BY date, meeting, race_number",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE actual_result IS NULL ORDER BY date, meeting, race_number"
            ).fetchall()
        return [dict(r) for r in rows]


def get_summary(days: int | None = None):
    """
    Return a summary dict with P&L statistics.

    Parameters
    ----------
    days : if set, restrict to last N days; None = all time

    Returns
    -------
    dict with keys:
      total_bets, settled_bets, win_count, win_rate_pct, roi_pct,
      total_profit_loss, current_streak, streak_type,
      by_tier: {tier: {bets, wins, profit_loss, roi_pct}}
      by_meeting: {meeting: {bets, wins, profit_loss}}
    """
    with _connect() as conn:
        _init_db(conn)

        where = "actual_result IS NOT NULL"
        params: list = []
        if days is not None:
            cutoff = (datetime.now(AEST) - timedelta(days=days)).strftime("%Y-%m-%d")
            where += " AND date >= ?"
            params.append(cutoff)

        rows = conn.execute(
            f"SELECT * FROM predictions WHERE {where} ORDER BY date, meeting, race_number, predicted_rank",
            params,
        ).fetchall()
        rows = [dict(r) for r in rows]

    total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

    if not rows:
        return {
            "total_bets": total,
            "settled_bets": 0,
            "win_count": 0,
            "win_rate_pct": 0.0,
            "roi_pct": 0.0,
            "total_profit_loss": 0.0,
            "current_streak": 0,
            "streak_type": "none",
            "by_tier": {},
            "by_meeting": {},
        }

    settled = len(rows)
    wins = sum(1 for r in rows if r["actual_result"] == 1)
    total_pl = sum(r["profit_loss"] for r in rows)
    total_staked = sum(r["stake"] for r in rows)
    roi_pct = (total_pl / total_staked * 100) if total_staked > 0 else 0.0
    win_rate = (wins / settled * 100) if settled > 0 else 0.0

    # Streak — walk backwards through results sorted chronologically
    streak = 0
    streak_type = "none"
    for r in reversed(rows):
        is_win = r["actual_result"] == 1
        if streak == 0:
            streak = 1
            streak_type = "win" if is_win else "loss"
        elif (streak_type == "win" and is_win) or (streak_type == "loss" and not is_win):
            streak += 1
        else:
            break

    # By tier
    tiers: dict = {}
    for r in rows:
        t = r["confidence_tier"] or "Unknown"
        if t not in tiers:
            tiers[t] = {"bets": 0, "wins": 0, "profit_loss": 0.0, "staked": 0.0}
        tiers[t]["bets"] += 1
        tiers[t]["wins"] += 1 if r["actual_result"] == 1 else 0
        tiers[t]["profit_loss"] += r["profit_loss"]
        tiers[t]["staked"] += r["stake"]
    by_tier = {
        t: {
            "bets": v["bets"],
            "wins": v["wins"],
            "profit_loss": round(v["profit_loss"], 2),
            "roi_pct": round(v["profit_loss"] / v["staked"] * 100, 1) if v["staked"] > 0 else 0.0,
        }
        for t, v in sorted(tiers.items())
    }

    # By meeting
    meetings: dict = {}
    for r in rows:
        m = r["meeting"]
        if m not in meetings:
            meetings[m] = {"bets": 0, "wins": 0, "profit_loss": 0.0}
        meetings[m]["bets"] += 1
        meetings[m]["wins"] += 1 if r["actual_result"] == 1 else 0
        meetings[m]["profit_loss"] += r["profit_loss"]
    by_meeting = {
        m: {
            "bets": v["bets"],
            "wins": v["wins"],
            "profit_loss": round(v["profit_loss"], 2),
        }
        for m, v in meetings.items()
    }

    return {
        "total_bets": total,
        "settled_bets": settled,
        "win_count": wins,
        "win_rate_pct": round(win_rate, 1),
        "roi_pct": round(roi_pct, 1),
        "total_profit_loss": round(total_pl, 2),
        "current_streak": streak,
        "streak_type": streak_type,
        "by_tier": by_tier,
        "by_meeting": by_meeting,
    }
