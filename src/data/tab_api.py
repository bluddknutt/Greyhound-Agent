"""
TAB API Client — fetches greyhound meetings, races, runners, and fixed odds
from the TAB public API (api.beta.tab.com.au).

TAB API details:
  - Auth: None (public API)
  - Geo-restriction: Australian IPs only (non-AU IPs silently fail)
  - Greyhound raceType param: G
  - Must use browser User-Agent header

Public API:
  fetch_meetings(date_str) → list[dict]
  fetch_race(date_str, venue_mnemonic, race_number) → dict | None
  fetch_all_races(date_str) → pd.DataFrame
"""

import logging
import time

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.beta.tab.com.au"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
}

# Maps TAB venue mnemonics to pkl model file names
VENUE_MNEMONIC_TO_MODEL = {
    "AP": "Angle Park",
    "BAL": "BALLARAT",
    "BEN": "BENDIGO",
}

# Rate limit between requests (seconds)
RATE_LIMIT = 0.3

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


def _api_get(url):
    """
    GET request to TAB API with retry logic and geo-restriction detection.

    Returns parsed JSON dict or None on failure.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)

            # Detect geo-restriction: TAB returns HTML or empty body for non-AU IPs
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                logger.error(
                    "TAB API returned HTML instead of JSON. "
                    "This API requires an Australian IP. "
                    "Current request may be geo-blocked."
                )
                return None

            if resp.status_code == 404:
                logger.warning("TAB API 404: %s", url)
                return None

            resp.raise_for_status()

            data = resp.json()
            if not data:
                logger.warning(
                    "TAB API returned empty response for %s. "
                    "This may indicate geo-restriction (Australian IPs only).",
                    url,
                )
                return None

            return data

        except requests.exceptions.JSONDecodeError:
            logger.error(
                "TAB API returned non-JSON response. "
                "This likely indicates geo-restriction (Australian IPs only)."
            )
            return None
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    "TAB API request failed (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, e,
                )
                time.sleep(RETRY_BACKOFF * (attempt + 1))
            else:
                logger.error("TAB API request failed after %d attempts: %s", MAX_RETRIES, e)
                return None

    return None


def fetch_meetings(date_str):
    """
    Fetch all greyhound meetings for a given date.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.

    Returns
    -------
    list[dict]
        List of meeting dicts with keys: venueMnemonic, meetingName,
        location, raceType, races (list of race numbers).
    """
    url = (
        f"{BASE_URL}/v1/tab-info-service/racing/dates/{date_str}"
        f"/meetings?jurisdiction=AUS"
    )

    data = _api_get(url)
    if not data:
        return []

    meetings = []
    # Navigate the TAB API response structure
    meeting_list = data.get("meetings", data) if isinstance(data, dict) else data
    if isinstance(meeting_list, dict):
        meeting_list = meeting_list.get("meetings", [])
    if not isinstance(meeting_list, list):
        meeting_list = [meeting_list] if meeting_list else []

    for meeting in meeting_list:
        if not isinstance(meeting, dict):
            continue

        race_type = meeting.get("raceType", "").upper()
        if race_type != "G":
            continue  # greyhounds only

        venue_mnemonic = meeting.get("venueMnemonic", "")
        meeting_name = meeting.get("meetingName", venue_mnemonic)
        location = meeting.get("location", "")

        # Extract race numbers from the meeting
        races_data = meeting.get("races", [])
        race_numbers = []
        if isinstance(races_data, list):
            for r in races_data:
                if isinstance(r, dict):
                    rn = r.get("raceNumber")
                    if rn is not None:
                        race_numbers.append(int(rn))
                elif isinstance(r, (int, float)):
                    race_numbers.append(int(r))

        meetings.append({
            "venueMnemonic": venue_mnemonic,
            "meetingName": meeting_name,
            "location": location,
            "raceType": race_type,
            "races": sorted(race_numbers) if race_numbers else [],
        })

    logger.info(
        "Fetched %d greyhound meetings for %s: %s",
        len(meetings),
        date_str,
        ", ".join(m["meetingName"] for m in meetings),
    )
    return meetings


def fetch_race(date_str, venue_mnemonic, race_number):
    """
    Fetch a single race with runners and odds.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.
    venue_mnemonic : str
        TAB venue mnemonic (e.g., 'AP', 'BAL').
    race_number : int
        Race number.

    Returns
    -------
    dict | None
        Race dict with keys: race_number, venue_mnemonic, venue_name,
        distance, grade, runners (list of runner dicts).
    """
    url = (
        f"{BASE_URL}/v1/tab-info-service/racing/dates/{date_str}"
        f"/meetings/G/{venue_mnemonic}/races/{race_number}"
    )

    data = _api_get(url)
    if not data:
        return None

    time.sleep(RATE_LIMIT)

    # Parse race metadata
    race_name = data.get("raceName", "")
    distance_str = data.get("distance", "0")
    try:
        distance = int(str(distance_str).replace("m", ""))
    except ValueError:
        distance = 0

    grade = data.get("raceClassConditions", data.get("raceClass", ""))

    # Parse runners
    runners_data = data.get("runners", [])
    runners = []

    for r in runners_data:
        if not isinstance(r, dict):
            continue

        # Skip scratched runners
        if r.get("scratched", False):
            continue

        runner_name = r.get("runnerName", "")
        runner_number = r.get("runnerNumber", 0)
        barrier = r.get("barrierNumber", runner_number)
        trainer = r.get("trainerName", r.get("trainerFullName", ""))

        # Fixed odds
        fixed_odds = r.get("fixedOdds", {})
        if isinstance(fixed_odds, dict):
            win_odds = fixed_odds.get("returnWin", None)
        else:
            win_odds = None

        # Career stats (may be nested)
        stats = r.get("stats", r.get("career", {}))
        if not isinstance(stats, dict):
            stats = {}

        # Last starts
        last_starts = r.get("last5Starts", r.get("formComment", ""))

        runners.append({
            "runnerName": runner_name,
            "runnerNumber": int(runner_number) if runner_number else 0,
            "barrierNumber": int(barrier) if barrier else 0,
            "trainerName": trainer,
            "fixedWinOdds": float(win_odds) if win_odds else None,
            "last5Starts": str(last_starts) if last_starts else "",
            "careerWins": _extract_stat(stats, ["wins", "totalWins"]),
            "careerPlaces": _extract_stat(stats, ["places", "totalPlaces"]),
            "careerStarts": _extract_stat(stats, ["starts", "totalStarts"]),
            "prizeMoney": _extract_stat(stats, ["prizemoney", "prizeMoney", "totalPrizeMoney"]),
            "weight": _extract_stat(stats, ["weight", "handicapWeight"]),
        })

    return {
        "race_number": race_number,
        "venue_mnemonic": venue_mnemonic,
        "venue_name": VENUE_MNEMONIC_TO_MODEL.get(venue_mnemonic, venue_mnemonic),
        "race_name": race_name,
        "distance": distance,
        "grade": grade,
        "runners": runners,
    }


def fetch_all_races(date_str):
    """
    Fetch all greyhound races for a date, returning a flat DataFrame
    with one row per runner.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns matching csv_ingest output schema plus
        odds-related columns.
    """
    meetings = fetch_meetings(date_str)
    if not meetings:
        logger.warning("No greyhound meetings found for %s", date_str)
        return pd.DataFrame()

    all_rows = []
    for meeting in meetings:
        venue_mn = meeting["venueMnemonic"]
        venue_name = meeting["meetingName"]

        for race_num in meeting["races"]:
            race = fetch_race(date_str, venue_mn, race_num)
            if not race or not race.get("runners"):
                continue

            for runner in race["runners"]:
                all_rows.append({
                    "dog_name": runner["runnerName"],
                    "dog_number": runner["runnerNumber"],
                    "sex": "",
                    "box": runner["barrierNumber"],
                    "weight": runner.get("weight", 0),
                    "distance": race["distance"],
                    "date": date_str,
                    "track": venue_mn,
                    "grade": race.get("grade", ""),
                    "race_number": race["race_number"],
                    "venue": venue_name,
                    "time": np.nan,  # not available pre-race
                    "win_time": np.nan,
                    "bon": np.nan,
                    "first_split": np.nan,
                    "margin": np.nan,
                    "w2g": "",
                    "pir": "",
                    "sp": runner.get("fixedWinOdds", np.nan),
                    "run_sequence": 1,
                    # Extra TAB-specific fields
                    "_odds": runner.get("fixedWinOdds"),
                    "_career_wins": runner.get("careerWins", 0),
                    "_career_places": runner.get("careerPlaces", 0),
                    "_career_starts": runner.get("careerStarts", 0),
                    "_prize_money": runner.get("prizeMoney", 0),
                    "_last5_starts": runner.get("last5Starts", ""),
                })

    if not all_rows:
        logger.warning("No runners fetched for %s", date_str)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    logger.info(
        "Fetched %d runners across %d venues, %d races for %s",
        len(df),
        len(meetings),
        df.groupby(["venue", "race_number"]).ngroups,
        date_str,
    )
    return df


def _extract_stat(stats_dict, keys):
    """Extract a stat value trying multiple possible key names."""
    for key in keys:
        val = stats_dict.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return 0
