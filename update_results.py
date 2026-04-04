"""
update_results.py — fetch actual race results from the TAB API and update P&L.

Usage:
    python update_results.py                     # resolve all pending predictions
    python update_results.py --date 2026-04-03   # resolve only that date

TAB API base: https://api.beta.tab.com.au/v1/tab-info-service/racing/
"""

import argparse
import re
import sys
from datetime import datetime, timezone, timedelta

import requests

from src.results_tracker import get_pending, update_result

AEST = timezone(timedelta(hours=11))
TAB_API = "https://api.beta.tab.com.au/v1/tab-info-service/racing"

# Venue-name → TAB venue-slug mappings for common GRV tracks
_VENUE_SLUG = {
    "the meadows": "The Meadows",
    "sandown park": "Sandown Park",
    "bendigo": "Bendigo",
    "ballarat": "Ballarat",
    "geelong": "Geelong",
    "shepparton": "Shepparton",
    "horsham": "Horsham",
    "warrnambool": "Warrnambool",
    "launceston": "Launceston",
    "hobart": "Hobart",
    "dapto": "Dapto",
    "richmond": "Richmond",
    "gosford": "Gosford",
    "wentworth park": "Wentworth Park",
    "albany": "Albany",
    "cannington": "Cannington",
    "mandurah": "Mandurah",
    "angle park": "Angle Park",
    "mount gambier": "Mount Gambier",
    "townsville": "Townsville",
    "cairns": "Cairns",
    "ipswich": "Ipswich",
    "gabba": "Gabba",
}


def _normalise_venue(meeting: str) -> str:
    """Return the meeting name unchanged; used for display."""
    return meeting


def fetch_meeting_results(date: str, meeting: str, race_number: int) -> dict | None:
    """
    Query the TAB API for a single race result.

    Returns a dict mapping dog_name (str) → finishing_position (int), or None on failure.
    """
    # TAB date format: YYYY-MM-DD
    # Endpoint: /racing/dates/{date}/meetings/{venue}/races/{race_number}
    venue_encoded = requests.utils.quote(meeting, safe="")
    url = f"{TAB_API}/dates/{date}/meetings/GRV/{venue_encoded}/races/{race_number}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"  [WARN] TAB API request failed for {meeting} R{race_number} {date}: {exc}")
        return None
    except ValueError:
        print(f"  [WARN] TAB API returned non-JSON for {meeting} R{race_number} {date}")
        return None

    runners = data.get("runners") or data.get("results") or []
    if not runners:
        # Try nested structure
        race = data.get("race") or {}
        runners = race.get("runners", [])

    if not runners:
        print(f"  [WARN] No runners found in TAB response for {meeting} R{race_number} {date}")
        return None

    positions: dict[str, int] = {}
    for runner in runners:
        name = (runner.get("runnerName") or runner.get("name") or "").strip().upper()
        pos = runner.get("finishingPosition") or runner.get("position")
        if name and pos is not None:
            try:
                positions[name] = int(pos)
            except (ValueError, TypeError):
                pass
    return positions or None


def _match_dog(name: str, positions: dict[str, int]) -> int | None:
    """Fuzzy-match dog name against TAB result names (case-insensitive)."""
    upper = name.strip().upper()
    if upper in positions:
        return positions[upper]
    # Partial match fallback
    for tab_name, pos in positions.items():
        if upper in tab_name or tab_name in upper:
            return pos
    return None


def resolve_predictions(date: str | None = None) -> tuple[int, int]:
    """
    Resolve all pending predictions (optionally filtered by date).

    Returns (resolved_count, failed_count).
    """
    pending = get_pending(date)
    if not pending:
        print("No pending predictions to resolve.")
        return 0, 0

    print(f"Found {len(pending)} pending prediction(s).")

    # Group by (date, meeting, race_number) to minimise API calls
    races: dict[tuple, list[dict]] = {}
    for row in pending:
        key = (row["date"], row["meeting"], row["race_number"])
        races.setdefault(key, []).append(row)

    resolved = 0
    failed = 0

    for (race_date, meeting, race_number), runners in sorted(races.items()):
        print(f"\n  Fetching: {meeting} Race {race_number} ({race_date})")
        positions = fetch_meeting_results(race_date, meeting, race_number)

        if positions is None:
            print(f"  [SKIP] Could not retrieve results.")
            failed += len(runners)
            continue

        print(f"  Results: {positions}")
        for row in runners:
            dog = row["dog_name"]
            pos = _match_dog(dog, positions)
            if pos is None:
                print(f"    [SKIP] {dog} — not found in result")
                failed += 1
                continue

            ok = update_result(meeting, race_number, race_date, dog, pos)
            if ok:
                pl_sign = "+" if pos == 1 else "-"
                print(f"    [OK] {dog}: finished {pos}st/nd/rd/th")
                resolved += 1
            else:
                print(f"    [ERR] Failed to update {dog}")
                failed += 1

    return resolved, failed


def main():
    parser = argparse.ArgumentParser(
        description="Resolve pending greyhound predictions against TAB API results."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Only resolve predictions for this date (default: all pending)",
    )
    args = parser.parse_args()

    if args.date:
        # Validate format
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: --date must be in YYYY-MM-DD format, got: {args.date}")
            sys.exit(1)

    resolved, failed = resolve_predictions(args.date)
    print(f"\nDone. Resolved: {resolved}  Failed/skipped: {failed}")


if __name__ == "__main__":
    main()
