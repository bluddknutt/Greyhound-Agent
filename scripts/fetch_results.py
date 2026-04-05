"""
Fetch today's actual race results and compute P&L against predictions.

Track normalisation:
  FastTrack API may return numeric codes ("400"), short abbreviations ("ALB"),
  or mixed-case names. Predictions store full human-readable names ("Albion Park").
  normalise_track_name() resolves all three cases.

Usage:
    python scripts/fetch_results.py          # print P&L for today
    python scripts/fetch_results.py 2025-11-25   # specific date
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from difflib import get_close_matches

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.mapping import trackCodes

AEST = timezone(timedelta(hours=11))

# ─────────────────────────────────────────────────────────────
# Track name lookup tables
# ─────────────────────────────────────────────────────────────

# FastTrack 3-letter abbreviations → canonical name
SHORT_CODE_MAP = {
    "ALB": "Albion Park",
    "ANG": "Angle Park",
    "ARM": "Armidale",
    "BAL": "Ballarat",
    "BEN": "Bendigo",
    "BEE": "Beenleigh",
    "BRM": "Barmera",
    "BUL": "Bulli",
    "BUN": "Bundaberg",
    "CAI": "Cairns",
    "CAN": "Cannington",
    "CAP": "Capalaba",
    "CAS": "Casino",
    "CES": "Cessnock",
    "CRA": "Cranbourne",
    "DAP": "Dapto",
    "DAR": "Darwin",
    "DEV": "Devonport",
    "DUB": "Dubbo",
    "GAW": "Gawler",
    "GEE": "Geelong",
    "GOC": "Gold Coast",
    "GOS": "Gosford",
    "GRA": "Grafton",
    "HEA": "Healesville",
    "HOB": "Hobart",
    "HOR": "Horsham",
    "IPS": "Ipswich",
    "LAU": "Launceston",
    "LAW": "Lawnton",
    "LIS": "Lismore",
    "MAI": "Maitland",
    "MAN": "Mandurah",
    "MEA": "The Meadows",
    "MUR": "Murray Bridge",
    "NEW": "Newcastle",
    "NOW": "Nowra",
    "ORA": "Orange",
    "PEN": "Penrith",
    "ROC": "Rockhampton",
    "SAL": "Sale",
    "SAN": "Sandown Park",
    "SHE": "Shepparton",
    "TOO": "Toowoomba",
    "TOW": "Townsville",
    "TRA": "Traralgon",
    "WAN": "Wangaratta",
    "WAG": "Wagga Wagga",
    "WAR": "Warragul",
    "WEN": "Wentworth Park",
    "WYO": "Wyong",
}

# Numeric trackCode → trackName  (e.g. "400" → "Albion Park")
TRACK_CODE_TO_NAME: dict = {str(t["trackCode"]): t["trackName"] for t in trackCodes}

# Lowercase trackName → canonical trackName  (for case-insensitive exact match)
TRACK_NAME_LOWER: dict = {t["trackName"].lower(): t["trackName"] for t in trackCodes}
_ALL_NAMES_LOWER = list(TRACK_NAME_LOWER.keys())


def normalise_track_name(raw: str) -> str:
    """
    Map any FastTrack track identifier to the canonical human-readable name.

    Resolution order:
      1. 3-letter short code (e.g. "ALB" → "Albion Park")
      2. Numeric code string  (e.g. "400" → "Albion Park")
      3. Case-insensitive exact name match
      4. Fuzzy match via difflib (cutoff=0.6)
      5. Return raw unchanged
    """
    if not raw:
        return raw
    s = str(raw).strip()

    # Short code lookup (upper-case)
    upper = s.upper()
    if upper in SHORT_CODE_MAP:
        return SHORT_CODE_MAP[upper]

    # Numeric code lookup
    if s.isdigit():
        return TRACK_CODE_TO_NAME.get(s, s)

    # Case-insensitive exact match
    lower = s.lower()
    if lower in TRACK_NAME_LOWER:
        return TRACK_NAME_LOWER[lower]

    # Fuzzy match
    matches = get_close_matches(lower, _ALL_NAMES_LOWER, n=1, cutoff=0.6)
    if matches:
        return TRACK_NAME_LOWER[matches[0]]

    return s


# ─────────────────────────────────────────────────────────────
# P&L computation
# ─────────────────────────────────────────────────────────────

def compute_pnl(predictions: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """
    Match top predictions against actual race winners and compute P&L.

    Parameters
    ----------
    predictions : DataFrame
        Columns required: Track, RaceNumber, DogName, FinalScore
        (output of main.py PDF pipeline or CSV picks.csv)
    results : DataFrame
        Columns required: track, race_number, winner
        `track` may be a numeric code, short code, or full name.

    Returns
    -------
    DataFrame with: track_normalised, RaceNumber, DogName, winner, correct, pnl
    """
    results = results.copy()
    results["track_normalised"] = results["track"].apply(normalise_track_name)

    predictions = predictions.copy()
    predictions["track_normalised"] = predictions["Track"].apply(normalise_track_name)

    # Top-scored pick per race
    top_picks = (
        predictions.sort_values("FinalScore", ascending=False)
        .groupby(["track_normalised", "RaceNumber"], sort=False)
        .head(1)
        .reset_index(drop=True)
    )

    merged = top_picks.merge(
        results[["track_normalised", "race_number", "winner"]],
        left_on=["track_normalised", "RaceNumber"],
        right_on=["track_normalised", "race_number"],
        how="inner",
    )

    merged["correct"] = (
        merged["DogName"].str.strip().str.lower()
        == merged["winner"].str.strip().str.lower()
    )
    merged["pnl"] = merged["correct"].map({True: 1.0, False: -1.0})

    return merged[["track_normalised", "RaceNumber", "DogName", "winner", "correct", "pnl"]]


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(AEST).strftime("%Y-%m-%d")

    picks_path = "outputs/picks.csv"
    results_path = f"outputs/results_{date_str}.csv"

    if not os.path.exists(picks_path):
        print(f"No picks file found at {picks_path} — run the prediction pipeline first.")
        sys.exit(0)

    if not os.path.exists(results_path):
        print(f"Results not yet available ({results_path} not found).")
        print("Re-run after races have finished and results are saved.")
        sys.exit(0)

    predictions = pd.read_csv(picks_path)
    results = pd.read_csv(results_path)

    pnl_df = compute_pnl(predictions, results)

    if pnl_df.empty:
        print("No matched races between picks and results.")
        sys.exit(0)

    print(f"\n=== P&L for {date_str} ===")
    print(pnl_df.to_string(index=False))
    wins = int(pnl_df["correct"].sum())
    n = len(pnl_df)
    net = pnl_df["pnl"].sum()
    print(f"\nResult: {wins}/{n} correct  |  Net: {net:+.2f} units")

    out = f"outputs/pnl_{date_str}.csv"
    pnl_df.to_csv(out, index=False)
    print(f"Saved → {out}")
