"""
update_results.py — CLI script to fetch actual race results from the TAB API
and populate the profit/loss fields for logged predictions.

Usage:
    python update_results.py                    # all pending predictions
    python update_results.py --date 2026-04-03  # only that date

TAB API base: https://api.beta.tab.com.au/v1/tab-info-service
"""

import argparse
import sys
import time
from datetime import datetime, date as date_type
from typing import Optional

import requests

from results_tracker import get_pending, update_result, _init_db, DB_PATH

TAB_BASE = "https://api.beta.tab.com.au/v1/tab-info-service"
JURISDICTION = "NSW"          # default jurisdiction for result lookups
REQUEST_TIMEOUT = 15          # seconds
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2             # seconds, doubled each retry


# ──────────────────────────────────────────
# TAB API helpers
# ──────────────────────────────────────────

def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    """GET with retry/backoff. Returns parsed JSON or None on failure."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            wait = RETRY_BACKOFF ** attempt
            print(f"  [warn] TAB API error (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(wait)
    return None


def fetch_meetings(race_date: str) -> list[dict]:
    """
    Return a list of meeting dicts for the given date.
    race_date: "YYYY-MM-DD"
    Each dict has keys: meetingName, meetingCode, venueCode, numRaces.
    """
    url = f"{TAB_BASE}/racing/dates/{race_date}/meetings"
    data = _get(url, params={"jurisdiction": JURISDICTION})
    if not data:
        return []
    meetings = data.get("meetings", [])
    # Filter to greyhound races only
    return [m for m in meetings if m.get("raceType", "").upper() in ("G", "GREYHOUND", "GH")]


def fetch_race_results(race_date: str, meeting_code: str, race_number: int) -> Optional[dict]:
    """
    Return result dict for a specific race, or None if unavailable.
    Result dict contains a 'runners' list with 'runnerName' and 'finishingPosition'.
    """
    url = (
        f"{TAB_BASE}/racing/dates/{race_date}"
        f"/meetings/{meeting_code}/races/{race_number}/results"
    )
    data = _get(url, params={"jurisdiction": JURISDICTION})
    return data


def _normalise_name(name: str) -> str:
    """Lower-case, strip punctuation for fuzzy matching."""
    return name.lower().strip().replace("'", "").replace("-", " ")


def find_finishing_position(result_data: dict, dog_name: str) -> Optional[int]:
    """
    Extract the finishing position for dog_name from a TAB result payload.
    Returns None if the dog wasn't found or result is unavailable.
    """
    if not result_data:
        return None

    runners = result_data.get("runners", [])
    needle = _normalise_name(dog_name)

    for runner in runners:
        api_name = _normalise_name(runner.get("runnerName", ""))
        if api_name == needle:
            pos = runner.get("finishingPosition")
            try:
                return int(pos)
            except (TypeError, ValueError):
                return None

    # Partial-match fallback
    for runner in runners:
        api_name = _normalise_name(runner.get("runnerName", ""))
        if needle in api_name or api_name in needle:
            pos = runner.get("finishingPosition")
            try:
                return int(pos)
            except (TypeError, ValueError):
                return None

    return None


def _find_meeting_code(meetings: list[dict], meeting_name: str) -> Optional[str]:
    """Match a stored meeting name to a TAB meeting code."""
    needle = _normalise_name(meeting_name)
    for m in meetings:
        if _normalise_name(m.get("meetingName", "")) == needle:
            return m.get("meetingCode") or m.get("venueCode")
        if needle in _normalise_name(m.get("meetingName", "")):
            return m.get("meetingCode") or m.get("venueCode")
    return None


# ──────────────────────────────────────────
# Main update logic
# ──────────────────────────────────────────

def update_for_date(target_date: str, dry_run: bool = False) -> int:
    """
    Fetch TAB results for target_date and update all pending predictions on that date.
    Returns the number of predictions updated.
    """
    pending = [p for p in get_pending() if p["date"] == target_date]
    if not pending:
        print(f"  No pending predictions for {target_date}.")
        return 0

    print(f"  Fetching TAB meetings for {target_date}…")
    meetings = fetch_meetings(target_date)
    if not meetings:
        print(f"  [warn] No TAB greyhound meetings found for {target_date}.")
        return 0

    print(f"  Found {len(meetings)} greyhound meeting(s).")
    updated = 0

    # Group pending predictions by (meeting, race_number)
    race_groups: dict[tuple, list[dict]] = {}
    for pred in pending:
        key = (pred["meeting"], pred["race_number"])
        race_groups.setdefault(key, []).append(pred)

    fetched_cache: dict[tuple, Optional[dict]] = {}

    for (meeting_name, race_number), preds in race_groups.items():
        meeting_code = _find_meeting_code(meetings, meeting_name)
        if not meeting_code:
            print(f"  [skip] Could not match meeting '{meeting_name}' in TAB data.")
            continue

        cache_key = (meeting_code, race_number)
        if cache_key not in fetched_cache:
            print(f"  Fetching R{race_number} @ {meeting_name} (code={meeting_code})…")
            fetched_cache[cache_key] = fetch_race_results(target_date, meeting_code, race_number)

        result_data = fetched_cache[cache_key]
        if not result_data:
            print(f"  [skip] No result data for R{race_number} @ {meeting_name}.")
            continue

        for pred in preds:
            pos = find_finishing_position(result_data, pred["dog_name"])
            if pos is None:
                print(f"  [skip] Could not find '{pred['dog_name']}' in result.")
                continue

            if dry_run:
                print(
                    f"  [dry-run] race_id={pred['race_id']} "
                    f"{pred['dog_name']} → finished {pos}"
                )
            else:
                update_result(pred["race_id"], pos)
                pl_symbol = "✓" if pos <= 3 else "✗"
                print(
                    f"  {pl_symbol} Updated race_id={pred['race_id']} "
                    f"{pred['dog_name']} → {pos}"
                )
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Fetch TAB race results and update prediction P&L."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Only update predictions for this date (default: all pending dates).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without writing to the database.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=DB_PATH,
        help=f"Path to SQLite database (default: {DB_PATH}).",
    )
    args = parser.parse_args()

    _init_db(args.db)
    pending = get_pending(args.db)

    if not pending:
        print("No pending predictions to update.")
        return

    if args.date:
        dates_to_process = [args.date]
    else:
        dates_to_process = sorted({p["date"] for p in pending})

    total_updated = 0
    for d in dates_to_process:
        print(f"\n--- {d} ---")
        total_updated += update_for_date(d, dry_run=args.dry_run)

    print(f"\nDone. {total_updated} prediction(s) updated.")


if __name__ == "__main__":
    main()
