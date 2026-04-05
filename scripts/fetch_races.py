"""
Fetch today's greyhound race data from two sources:
  1. thedogs.com.au web scraper (src/scrapers/scrape_form_guide.py)
  2. TAB API stub — replace the placeholder section below once you have a key

Outputs:
  data/form_guide_YYYY-MM-DD.csv   (from scraper)

Usage:
  python3 scripts/fetch_races.py
  python3 scripts/fetch_races.py --date 2026-04-05
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or scripts/ directory
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

AEST = timezone(timedelta(hours=10))  # AEST (UTC+10)


# ---------------------------------------------------------------------------
# Source 1: thedogs.com.au scraper
# ---------------------------------------------------------------------------
def fetch_via_scraper(date_str: str, output_path: Path) -> int:
    """Scrape upcoming race fields from thedogs.com.au. Returns row count."""
    from src.scrapers.scrape_form_guide import scrape_all_upcoming
    import pandas as pd

    cutoff = datetime.now(AEST)
    print(f"[scraper] Fetching venues for {date_str} (cutoff={cutoff.strftime('%H:%M AEST')})...")
    runners = scrape_all_upcoming(date_str, cutoff)

    if not runners:
        print("[scraper] WARNING: No upcoming races found.")
        return 0

    df = pd.DataFrame(runners)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"[scraper] Saved {len(df)} runners to {output_path}")
    return len(df)


# ---------------------------------------------------------------------------
# Source 2: TAB API stub
# ---------------------------------------------------------------------------
def fetch_via_tab_api(date_str: str) -> list:
    """
    TAB API integration stub.

    Replace this function body with real TAB API calls once you have access.
    Documentation: https://api.tab.com.au  (check current TAB API docs)

    Expected return: list of race dicts compatible with scraper output columns:
      venue, state, race_number, race_name, race_time, distance, grade,
      box, dog_name, trainer, best_time, last_4_starts, last_start
    """
    tab_key = os.environ.get("TAB_API_KEY", "")

    if not tab_key or tab_key == "your_tab_api_key_here":
        print("[TAB API] No TAB_API_KEY configured — skipping TAB API fetch.")
        return []

    print(f"[TAB API] TAB_API_KEY found — attempting fetch for {date_str}...")

    # --- Replace everything below this line with real TAB API calls ---
    # Example structure (pseudo-code):
    #
    # import requests
    # BASE = "https://api.tab.com.au/v1"
    # headers = {"Authorization": f"Bearer {tab_key}"}
    # resp = requests.get(f"{BASE}/racing/dates/{date_str}/meetings", headers=headers, timeout=30)
    # resp.raise_for_status()
    # meetings = resp.json()["meetings"]
    # runners = []
    # for meeting in meetings:
    #     for race in meeting["races"]:
    #         for runner in race["runners"]:
    #             runners.append({
    #                 "venue": meeting["venueName"],
    #                 "state": meeting["state"],
    #                 "race_number": race["raceNumber"],
    #                 "race_name": race["raceName"],
    #                 "race_time": race["startTime"],
    #                 "distance": race["distance"],
    #                 "grade": race.get("grade", ""),
    #                 "box": runner["barrierNumber"],
    #                 "dog_name": runner["runnerName"],
    #                 "trainer": runner.get("trainerName", ""),
    #                 "best_time": runner.get("bestTime", ""),
    #                 "last_4_starts": runner.get("recentForm", ""),
    #                 "last_start": "",
    #             })
    # return runners

    print("[TAB API] STUB: Real TAB API call not yet implemented. Returning empty list.")
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch today's greyhound race data")
    parser.add_argument("--date", default=None, help="Date in YYYY-MM-DD (default: today AEST)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(AEST).strftime("%Y-%m-%d")
    output_path = REPO_ROOT / "data" / f"form_guide_{date_str}.csv"

    print(f"=== fetch_races.py | date={date_str} ===")

    # Source 1: scraper
    scraper_count = fetch_via_scraper(date_str, output_path)

    # Source 2: TAB API (merge results if any)
    tab_runners = fetch_via_tab_api(date_str)
    if tab_runners:
        import pandas as pd
        tab_df = pd.DataFrame(tab_runners)
        if output_path.exists():
            existing = pd.read_csv(output_path)
            merged = pd.concat([existing, tab_df], ignore_index=True).drop_duplicates(
                subset=["venue", "race_number", "box"]
            )
        else:
            merged = tab_df
        merged.to_csv(output_path, index=False)
        print(f"[TAB API] Merged {len(tab_runners)} TAB runners. Total: {len(merged)} rows.")

    total = scraper_count + len(tab_runners)
    if total == 0:
        print("ERROR: No race data fetched from any source. Exiting.")
        sys.exit(1)

    print(f"=== fetch_races.py complete: {total} runners fetched ===")


if __name__ == "__main__":
    main()
