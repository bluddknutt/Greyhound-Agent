"""
Export today's top picks from outputs/picks.csv → latest_picks.json

The JSON file is committed to the repo root so the Vercel site can read it
via a static file fetch.

Output format:
{
  "date": "2026-04-05",
  "generated_at": "2026-04-05T07:12:34+10:00",
  "total_picks": 12,
  "picks": [
    {
      "track": "Wentworth Park",
      "race_number": 3,
      "box": 5,
      "dog_name": "Zippy Joe",
      "final_score": 72.4,
      "bet_type": "win",
      "prize_money": 1250.0,
      ...
    },
    ...
  ]
}

Usage:
  python3 scripts/export_json.py
  python3 scripts/export_json.py --date 2026-04-05
  python3 scripts/export_json.py --picks outputs/picks.csv --out latest_picks.json
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

AEST = timezone(timedelta(hours=10))

# Columns to include in the JSON output (in order)
EXPORT_COLS = [
    "Track", "RaceNumber", "Box", "DogName", "FinalScore",
    "PrizeMoney", "Trainer", "Distance", "BestTimeSec",
    "CareerWins", "CareerStarts", "FormMomentum", "BoxBiasFactor",
]

# Maps CSV column names → JSON field names (snake_case)
COL_RENAME = {
    "Track": "track",
    "RaceNumber": "race_number",
    "Box": "box",
    "DogName": "dog_name",
    "FinalScore": "final_score",
    "PrizeMoney": "prize_money",
    "Trainer": "trainer",
    "Distance": "distance",
    "BestTimeSec": "best_time_sec",
    "CareerWins": "career_wins",
    "CareerStarts": "career_starts",
    "FormMomentum": "form_momentum",
    "BoxBiasFactor": "box_bias_factor",
}


def _clean(value):
    """Convert numpy/nan values to JSON-safe types."""
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
        return float(value) if isinstance(value, float) else value
    except (TypeError, ValueError):
        return value


def export_json(
    picks_path: Path,
    output_path: Path,
    date_str: str,
) -> int:
    import pandas as pd
    from scripts.init_db import get_db_path
    from scripts.log_predictions import determine_bet_type

    if not picks_path.exists():
        print(f"ERROR: picks file not found: {picks_path}")
        sys.exit(1)

    df = pd.read_csv(picks_path)
    if df.empty:
        print("WARNING: picks.csv is empty — writing empty picks JSON.")

    picks_list = []
    for _, row in df.iterrows():
        pick = {}
        for csv_col, json_key in COL_RENAME.items():
            val = row.get(csv_col)
            pick[json_key] = _clean(val)

        score = float(row.get("FinalScore", 0))
        pick["bet_type"] = determine_bet_type(score)
        picks_list.append(pick)

    # Sort by final_score descending
    picks_list.sort(key=lambda p: p.get("final_score") or 0, reverse=True)

    payload = {
        "date": date_str,
        "generated_at": datetime.now(AEST).isoformat(timespec="seconds"),
        "total_picks": len(picks_list),
        "picks": picks_list,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(picks_list)} picks to {output_path}")
    return len(picks_list)


def main():
    parser = argparse.ArgumentParser(description="Export picks.csv to latest_picks.json")
    parser.add_argument("--date", default=None, help="Race date YYYY-MM-DD (default: today AEST)")
    parser.add_argument("--picks", default=None, help="Path to picks CSV")
    parser.add_argument("--out", default=None, help="Output JSON path (default: latest_picks.json)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(AEST).strftime("%Y-%m-%d")
    picks_path = Path(args.picks) if args.picks else REPO_ROOT / "outputs" / "picks.csv"
    output_path = Path(args.out) if args.out else REPO_ROOT / "latest_picks.json"

    print(f"=== export_json.py | date={date_str} ===")
    count = export_json(picks_path, output_path, date_str)
    print(f"=== export_json.py complete: {count} picks written ===")


if __name__ == "__main__":
    main()
