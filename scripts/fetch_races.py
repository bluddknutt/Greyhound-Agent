"""
Fetch today's greyhound race form guide and save to CSV.

Wraps src/scrapers/scrape_form_guide.py.
Output: outputs/form_guide_YYYY-MM-DD.csv

Run from project root:
    python scripts/fetch_races.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.scrape_form_guide import scrape_all_upcoming

AEST = timezone(timedelta(hours=11))  # AEDT; TZ env var set by run_now.sh handles DST


if __name__ == "__main__":
    now = datetime.now(AEST)
    date_str = now.strftime("%Y-%m-%d")

    print(f"Fetching races for {date_str}...")
    all_data = scrape_all_upcoming(date_str, now)

    if not all_data:
        print("No race data found for today.")
        sys.exit(1)

    os.makedirs("outputs", exist_ok=True)
    df = pd.DataFrame(all_data)
    path = f"outputs/form_guide_{date_str}.csv"
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} runners → {path}")
