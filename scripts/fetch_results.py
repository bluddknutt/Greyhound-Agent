"""
Fetch today's race results and compute P&L against predictions.

Track normalisation maps FastTrack codes / short abbreviations to the
canonical full names stored in predictions (e.g. "ALB" → "Albion Park").

Run from project root:
    python scripts/fetch_results.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from difflib import get_close_matches

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.mapping import trackCodes

AEST = timezone(timedelta(hours=11))

# ── Track name lookup tables ─────────────────────────────────────────────────

# FastTrack 3-letter abbreviations → canonical full name
SHORT_CODE_MAP = {
    "ALB": "Albion Park",
    "ANG": "Angle Park",
    "BAL": "Ballarat",
    "BEN": "Bendigo",
    "BUL": "Bulli",
    "CAN": "Cannington",
    "CAP": "Capalaba",
    "CAS": "Casino",
    "CRN": "Cranbourne",
    "DAP": "Dapto",
    "DAR": "Darwin",
    "DEV": "Devonport",
    "GAW": "Gawler",
    "GEE": "Geelong",
    "GLD": "Gold Coast",
    "GRF": "Grafton",
    "HOB": "Hobart",
    "HOR": "Horsham",
    "IPS": "Ipswich",
    "LAU": "Launceston",
    "LIS": "Lismore",
    "MAN": "Mandurah",
    "MAI": "Maitland",
    "MAK": "Mackay",
    "MEA": "The Meadows",
    "MTG": "Mount Gambier",
    "MTI": "Mt Isa",
    "MBR": "Murray Bridge",
    "NEW": "Newcastle",
    "ROC": "Rockhampton",
    "SAL": "Sale",
    "SAN": "Sandown Park",
    "SHE": "Shepparton",
    "TOO": "Toowoomba",
    "TOW": "Townsville",
    "TRA": "Traralgon",
    "WAG": "Wagga Wagga",
    "WAN": "Wangaratta",
    "WNP": "Wentworth Park",
    "WYO": "Wyong",
}

# Numeric code → canonical name (from mapping.py)
_CODE_TO_NAME: dict[str, str] = {str(t["trackCode"]): t["trackName"] for t in trackCodes}

# Lower-case name → canonical name
_NAME_LOWER: dict[str, str] = {t["trackName"].lower(): t["trackName"] for t in trackCodes}
_ALL_NAMES_LOWER = list(_NAME_LOWER.keys())


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalise_track_name(raw: str) -> str:
    """
    Map a FastTrack identifier to the canonical human-readable track name.

    Resolution order:
      1. 3-letter short code (e.g. "ALB" → "Albion Park")
      2. Numeric track code  (e.g. "400" → "Albion Park")
      3. Case-insensitive exact match (e.g. "albion park" → "Albion Park")
      4. Fuzzy match against all known names (cutoff 0.6)
      5. Return raw value unchanged
    """
    if not raw:
        return raw
    s = str(raw).strip()

    # 1. Short alphabetic code
    upper = s.upper()
    if upper in SHORT_CODE_MAP:
        return SHORT_CODE_MAP[upper]

    # 2. Numeric code
    if s.isdigit():
        return _CODE_TO_NAME.get(s, s)

    # 3. Exact case-insensitive
    lower = s.lower()
    if lower in _NAME_LOWER:
        return _NAME_LOWER[lower]

    # 4. Fuzzy match
    matches = get_close_matches(lower, _ALL_NAMES_LOWER, n=1, cutoff=0.6)
    if matches:
        return _NAME_LOWER[matches[0]]

    return s


# ── P&L computation ───────────────────────────────────────────────────────────

def compute_pnl(predictions: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """
    Match top predictions against actual race winners and return a P&L table.

    Parameters
    ----------
    predictions : DataFrame
        Must contain: Track (human-readable), RaceNumber, DogName, FinalScore
    results : DataFrame
        Must contain: track (code or name), race_number, winner

    Returns
    -------
    DataFrame with: track_normalised, RaceNumber, DogName, winner, correct, pnl
    """
    results = results.copy()
    results["track_normalised"] = results["track"].apply(normalise_track_name)

    predictions = predictions.copy()
    predictions["track_normalised"] = predictions["Track"].apply(normalise_track_name)

    # One top pick per race
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


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    now = datetime.now(AEST)
    date_str = now.strftime("%Y-%m-%d")

    picks_path = "outputs/picks.csv"
    results_path = f"outputs/results_{date_str}.csv"

    if not os.path.exists(picks_path):
        print(f"No picks found at {picks_path} — run main.py first.")
        sys.exit(0)

    predictions = pd.read_csv(picks_path)

    if not os.path.exists(results_path):
        print(f"Results not yet available ({results_path} not found).")
        print("Re-run after today's races have finished.")
        sys.exit(0)

    results = pd.read_csv(results_path)
    pnl_df = compute_pnl(predictions, results)

    if pnl_df.empty:
        print("No matching races found between picks and results.")
        sys.exit(0)

    print("\n=== P&L Summary ===")
    print(pnl_df.to_string(index=False))
    net = pnl_df["pnl"].sum()
    wins = int(pnl_df["correct"].sum())
    n = len(pnl_df)
    print(f"\nNet: {net:+.2f} units  |  {wins}/{n} correct ({wins/n:.0%})")

    out_path = f"outputs/pnl_{date_str}.csv"
    pnl_df.to_csv(out_path, index=False)
    print(f"Saved → {out_path}")
