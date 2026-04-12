"""
Bet Selector — applies value-betting overlay logic to model predictions.

Overlay formula: overlay_pct = (model_prob * odds - 1) * 100
Threshold: 10% default. One best-bet per race.

When no live odds available (CSV source), ranks by model probability alone
and flags as "no odds available — model rank only".

Public API:
  select_bets(predictions_df, config) → list[dict]
  format_picks_json(picks, date_str, source) → dict
"""

import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

AEST = timezone(timedelta(hours=10))

DEFAULT_OVERLAY_THRESHOLD = 10.0  # percent
DEFAULT_BET_AMOUNT = 10.0  # AUD


def select_bets(predictions_df, config=None):
    """
    Select value bets from model predictions.

    Parameters
    ----------
    predictions_df : pd.DataFrame
        Must have columns: _dog_name, _venue, _race_number, _dog_number,
        model_prob. Optionally _odds for live odds.
    config : dict, optional
        Pipeline config. Reads tracking.bet_amount and tracking.min_overlay_pct.

    Returns
    -------
    list[dict]
        List of pick dicts for latest_picks.json.
    """
    if predictions_df.empty:
        logger.warning("No predictions to select bets from")
        return []

    config = config or {}
    tracking = config.get("tracking", {})
    bet_amount = float(tracking.get("bet_amount", DEFAULT_BET_AMOUNT))
    overlay_threshold = float(tracking.get("min_overlay_pct", DEFAULT_OVERLAY_THRESHOLD))

    has_odds = "_odds" in predictions_df.columns and predictions_df["_odds"].notna().any()

    picks = []
    race_groups = predictions_df.groupby(["_venue", "_race_number"])

    for (venue, race_num), race_df in race_groups:
        race_df = race_df.sort_values("model_prob", ascending=False)

        if has_odds and race_df["_odds"].notna().any():
            # Value betting mode: select best overlay
            best_pick = _select_best_overlay(
                race_df, venue, race_num, bet_amount, overlay_threshold
            )
        else:
            # No odds mode: select by model probability
            best_pick = _select_by_probability(
                race_df, venue, race_num, bet_amount
            )

        if best_pick:
            picks.append(best_pick)

    logger.info("Selected %d bets from %d races", len(picks), len(race_groups))
    return picks


def _select_best_overlay(race_df, venue, race_num, bet_amount, threshold):
    """Select the runner with the best overlay above threshold."""
    best = None

    for _, row in race_df.iterrows():
        odds = row.get("_odds")
        prob = row.get("model_prob", 0)

        if pd.isna(odds) or odds <= 1.0 or pd.isna(prob) or prob <= 0:
            continue

        overlay = (prob * odds - 1) * 100

        if overlay > threshold:
            if best is None or overlay > best["overlay_pct"]:
                # Find danger runner (2nd highest prob)
                danger = _get_danger_runner(race_df, row["_dog_name"])

                best = {
                    "venue": venue,
                    "race_number": int(race_num),
                    "dog_name": row["_dog_name"],
                    "box": int(row.get("_dog_number", 0)) if pd.notna(row.get("_dog_number")) else 0,
                    "model_prob": round(float(prob), 4),
                    "odds": round(float(odds), 2),
                    "overlay_pct": round(float(overlay), 1),
                    "confidence": _confidence_level(overlay),
                    "bet_amount": bet_amount,
                    "danger": danger,
                }

    return best


def _select_by_probability(race_df, venue, race_num, bet_amount):
    """Select the top runner by model probability (no odds available)."""
    if race_df.empty:
        return None

    top = race_df.iloc[0]
    prob = top.get("model_prob", 0)

    if pd.isna(prob) or prob <= 0:
        return None

    danger = _get_danger_runner(race_df, top["_dog_name"])

    return {
        "venue": venue,
        "race_number": int(race_num),
        "dog_name": top["_dog_name"],
        "box": int(top.get("_dog_number", 0)) if pd.notna(top.get("_dog_number")) else 0,
        "model_prob": round(float(prob), 4),
        "odds": None,
        "overlay_pct": None,
        "confidence": _probability_confidence(prob),
        "bet_amount": bet_amount,
        "danger": danger,
    }


def _get_danger_runner(race_df, exclude_name):
    """Get the second-highest probability runner as the 'danger'."""
    others = race_df[race_df["_dog_name"] != exclude_name]
    if others.empty:
        return None

    danger = others.iloc[0]
    return {
        "dog_name": danger["_dog_name"],
        "box": int(danger.get("_dog_number", 0)) if pd.notna(danger.get("_dog_number")) else 0,
        "model_prob": round(float(danger.get("model_prob", 0)), 4),
    }


def _confidence_level(overlay_pct):
    """Map overlay percentage to confidence label."""
    if overlay_pct >= 30:
        return "HIGH"
    elif overlay_pct >= 15:
        return "MEDIUM"
    else:
        return "LOW"


def _probability_confidence(prob):
    """Map raw probability to confidence label (no odds mode)."""
    if prob >= 0.35:
        return "HIGH"
    elif prob >= 0.20:
        return "MEDIUM"
    else:
        return "LOW"


def format_picks_json(picks, date_str, source="csv"):
    """
    Wrap picks into the latest_picks.json schema.

    Parameters
    ----------
    picks : list[dict]
        List of pick dicts from select_bets().
    date_str : str
        Date string (YYYY-MM-DD).
    source : str
        Data source: 'csv', 'tab', or 'scrape'.

    Returns
    -------
    dict
        JSON-serializable dict matching latest_picks.json schema.
    """
    now = datetime.now(AEST)

    # Compute summary
    probs = [p["model_prob"] for p in picks if p.get("model_prob")]
    avg_prob = round(float(np.mean(probs)), 4) if probs else 0.0

    # Count unique races
    races = set()
    for p in picks:
        races.add((p.get("venue", ""), p.get("race_number", 0)))

    return {
        "generated_at": now.isoformat(),
        "source": source,
        "date": date_str,
        "picks": picks,
        "summary": {
            "total_races": len(races),
            "total_picks": len(picks),
            "avg_model_prob": avg_prob,
        },
    }
