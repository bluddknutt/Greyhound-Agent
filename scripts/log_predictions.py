"""
Log today's predictions from outputs/picks.csv into the SQLite database.

Reads the top-pick per race (picks.csv), determines bet type from score
thresholds (config.py), and upserts into the predictions table.

Usage:
  python3 scripts/log_predictions.py
  python3 scripts/log_predictions.py --date 2026-04-05
  python3 scripts/log_predictions.py --picks outputs/picks.csv
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

AEST = timezone(timedelta(hours=10))


def determine_bet_type(score: float) -> str:
    """Map final score to bet type using thresholds from config.py."""
    try:
        from src.config import SCORING_WEIGHTS
        win_threshold = SCORING_WEIGHTS.get("win_threshold", 60)
        place_threshold = SCORING_WEIGHTS.get("place_threshold", 45)
    except ImportError:
        win_threshold, place_threshold = 60, 45

    if score >= win_threshold:
        return "win"
    elif score >= place_threshold:
        return "place"
    return "watch"


def log_predictions(picks_path: Path, date_str: str, db_path: str | None = None) -> int:
    import pandas as pd
    from scripts.init_db import init_db

    if not picks_path.exists():
        print(f"ERROR: picks file not found: {picks_path}")
        sys.exit(1)

    df = pd.read_csv(picks_path)
    if df.empty:
        print("WARNING: picks.csv is empty — nothing to log.")
        return 0

    conn = init_db(db_path)
    inserted = 0

    for _, row in df.iterrows():
        score = float(row.get("FinalScore", 0))
        bet_type = determine_bet_type(score)

        try:
            conn.execute(
                """
                INSERT INTO predictions
                    (race_date, track, race_number, box, dog_name, final_score, bet_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(race_date, track, race_number, box)
                DO UPDATE SET
                    dog_name    = excluded.dog_name,
                    final_score = excluded.final_score,
                    bet_type    = excluded.bet_type,
                    created_at  = datetime('now','localtime')
                """,
                (
                    date_str,
                    str(row.get("Track", "")),
                    int(row.get("RaceNumber", 0)),
                    int(row.get("Box", 0)) if pd.notna(row.get("Box")) else None,
                    str(row.get("DogName", "")),
                    score,
                    bet_type,
                ),
            )
            inserted += 1
        except Exception as exc:
            print(f"  WARN: could not insert row {dict(row)}: {exc}")

    conn.commit()
    conn.close()

    print(f"Logged {inserted} predictions for {date_str}:")
    for _, row in df.iterrows():
        score = float(row.get("FinalScore", 0))
        bt = determine_bet_type(score)
        print(
            f"  {row.get('Track')} R{row.get('RaceNumber')} "
            f"Box {row.get('Box')} {row.get('DogName')} "
            f"score={score:.2f} [{bt}]"
        )
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Log picks.csv predictions to SQLite")
    parser.add_argument("--date", default=None, help="Race date YYYY-MM-DD (default: today AEST)")
    parser.add_argument("--picks", default=None, help="Path to picks CSV (default: outputs/picks.csv)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(AEST).strftime("%Y-%m-%d")
    picks_path = Path(args.picks) if args.picks else REPO_ROOT / "outputs" / "picks.csv"

    print(f"=== log_predictions.py | date={date_str} ===")
    count = log_predictions(picks_path, date_str)
    print(f"=== log_predictions.py complete: {count} rows inserted ===")


if __name__ == "__main__":
    main()
