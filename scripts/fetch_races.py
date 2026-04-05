"""
Fetch today's upcoming race form data from thedogs.com.au and save to CSV.

Usage (called by run_now.sh — TZ is already set):
    python scripts/fetch_races.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.scrape_form_guide import scrape_all_upcoming

AEST = timezone(timedelta(hours=11))  # AEDT; AEST is +10 but TZ env var handles DST

if __name__ == "__main__":
    now = datetime.now(AEST)
    date_str = now.strftime("%Y-%m-%d")

    print(f"Fetching form guide for {date_str} (AEST)...")
    all_data = scrape_all_upcoming(date_str, now)

    if not all_data:
        print("No race data found for today.")
        sys.exit(1)

    os.makedirs("outputs", exist_ok=True)
    df = pd.DataFrame(all_data)
    out_path = f"outputs/form_guide_{date_str}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} runners across {df['venue'].nunique()} venues → {out_path}")
