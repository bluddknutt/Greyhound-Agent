"""Service layer for the TAB pipeline.

This module wraps the existing TAB pipeline logic so it can be reused by
CLI runners and web/API callers.
"""

from __future__ import annotations

import json
import os
import pickle
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.bet_selector import format_picks_json, select_bets
from src.config_loader import load_config
from src.data.csv_ingest import load_meeting_csvs
from src.data.tab_api import fetch_all_races
from src.scrapers.thedogs_scraper import scrape_print_hub
from src.tab_feature_engineer import MODEL_FEATURES, engineer_features

AEST = timezone(timedelta(hours=10))
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VENUE_MODEL_NAMES = {
    "Angle Park": "Angle Park",
    "angle park": "Angle Park",
    "AP": "Angle Park",
    "BALLARAT": "BALLARAT",
    "Ballarat": "BALLARAT",
    "ballarat": "BALLARAT",
    "BAL": "BALLARAT",
    "BENDIGO": "BENDIGO",
    "Bendigo": "BENDIGO",
    "bendigo": "BENDIGO",
    "BEN": "BENDIGO",
}


@dataclass
class PipelineOptions:
    source: str = "csv"
    date: str | None = None
    venue: str | None = None
    csv_dir: str = "./race_data/"
    dry_run: bool = False


def resolve_date(date_str: str | None) -> str:
    return date_str or datetime.now(AEST).strftime("%Y-%m-%d")


def load_venue_models(venue_name: str):
    """Load pkl models for a venue.

    Returns (gb_model, rf_model, scaler) or None if not available.
    """
    model_prefix = VENUE_MODEL_NAMES.get(venue_name)
    if not model_prefix:
        for key, val in VENUE_MODEL_NAMES.items():
            if key.lower() == venue_name.lower():
                model_prefix = val
                break

    if not model_prefix:
        return None

    gb_path = os.path.join(_HERE, f"{model_prefix}_gb.pkl")
    rf_path = os.path.join(_HERE, f"{model_prefix}_rf.pkl")
    scaler_path = os.path.join(_HERE, f"{model_prefix}_scaler.pkl")

    if not all(os.path.exists(p) for p in [gb_path, rf_path, scaler_path]):
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with open(gb_path, "rb") as f:
                gb = pickle.load(f)
            with open(rf_path, "rb") as f:
                rf = pickle.load(f)
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)

        return gb, rf, scaler
    except Exception:
        return None


def apply_composite_fallback(features_df: pd.DataFrame, mask: pd.Series):
    """Apply composite scoring fallback for rows in the supplied mask."""
    venue_df = features_df.loc[mask]
    for _, race_group in venue_df.groupby("_race_number"):
        idx = race_group.index
        scores = race_group["FinalScore"]
        total = scores.sum()
        if total > 0:
            features_df.loc[idx, "model_prob"] = scores / total
        else:
            features_df.loc[idx, "model_prob"] = 1.0 / len(race_group)


def predict_with_models(features_df: pd.DataFrame) -> pd.DataFrame:
    """Run model inference with venue-model and fallback scoring support."""
    features_df = features_df.copy()
    features_df["model_prob"] = np.nan

    venues = features_df["_venue"].unique()

    for venue in venues:
        venue_mask = features_df["_venue"] == venue
        venue_df = features_df.loc[venue_mask]
        models = load_venue_models(venue)

        if models:
            gb, rf, scaler = models
            try:
                X = venue_df[MODEL_FEATURES].values
                X_scaled = scaler.transform(X)
                gb_probs = gb.predict_proba(X_scaled)[:, 1]
                rf_probs = rf.predict_proba(X_scaled)[:, 1]
                features_df.loc[venue_mask, "model_prob"] = (gb_probs + rf_probs) / 2
            except Exception:
                apply_composite_fallback(features_df, venue_mask)
        else:
            apply_composite_fallback(features_df, venue_mask)

    return features_df


def _load_raw_data(options: PipelineOptions, config: dict[str, Any]) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    source = options.source
    date_str = resolve_date(options.date)
    csv_dir = options.csv_dir
    metadata: dict[str, Any] = {"source": source}

    if source == "scrape":
        download_dir = config.get("scraper", {}).get("download_dir", "./downloads/")
        scrape_results = scrape_print_hub(date_str, download_dir, options.venue)
        if not scrape_results:
            raise RuntimeError("No files downloaded from Print Hub")
        csv_dir = os.path.join(download_dir, date_str)
        metadata["scrape_results"] = scrape_results

    if source in ("csv", "scrape"):
        raw_df = load_meeting_csvs(csv_dir, venue=options.venue)
        if raw_df.empty:
            raise RuntimeError(f"No race data found in {csv_dir}")
    elif source == "tab":
        raw_df = fetch_all_races(date_str)
        if raw_df.empty:
            raise RuntimeError("No data from TAB API. Australian IP may be required.")
        if options.venue:
            raw_df = raw_df[
                raw_df["venue"].str.lower().str.contains(options.venue.lower())
                | raw_df["track"].str.lower().str.contains(options.venue.lower())
            ]
    else:
        raise ValueError(f"Unsupported source: {source}")

    return raw_df, date_str, metadata


def _prediction_records(predictions_df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for (venue, race_num), race_df in predictions_df.groupby(["_venue", "_race_number"]):
        race_ranked = race_df.sort_values("model_prob", ascending=False)
        runners = []
        for rank, (_, row) in enumerate(race_ranked.iterrows(), 1):
            odds = row.get("Odds")
            overlay_pct = row.get("overlay_pct")
            runners.append(
                {
                    "rank": rank,
                    "box": int(row.get("_dog_number", 0)) if pd.notna(row.get("_dog_number")) else None,
                    "dog_name": str(row.get("_dog_name", "")),
                    "model_prob": float(row.get("model_prob", 0.0)),
                    "final_score": float(row.get("FinalScore", 0.0)),
                    "odds": float(odds) if pd.notna(odds) else None,
                    "overlay_pct": float(overlay_pct) if pd.notna(overlay_pct) else None,
                }
            )
        records.append({"venue": str(venue), "race_number": int(race_num), "runners": runners})
    return records


def run_pipeline(options: PipelineOptions) -> dict[str, Any]:
    """Run the prediction pipeline and return structured data."""
    config = load_config()
    raw_df, date_str, metadata = _load_raw_data(options, config)

    features_df = engineer_features(raw_df)
    if features_df.empty:
        raise RuntimeError("Feature engineering produced no output")

    predictions_df = predict_with_models(features_df)
    picks = select_bets(predictions_df, config)

    n_runners = int(len(raw_df))
    n_venues = int(raw_df["venue"].nunique()) if "venue" in raw_df.columns else 0
    n_races = int(raw_df.groupby(["venue", "race_number"]).ngroups) if not raw_df.empty else 0

    picks_json = format_picks_json(picks, date_str, source=options.source)

    output_paths = {}
    if not options.dry_run:
        outputs_dir = os.path.join(_HERE, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        latest_path = os.path.join(_HERE, "latest_picks.json")
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(picks_json, f, indent=2, default=str)

        csv_path = os.path.join(outputs_dir, f"tab_picks_{date_str}.csv")
        if picks:
            pd.DataFrame(
                [
                    {
                        "venue": p["venue"],
                        "race": p["race_number"],
                        "box": p["box"],
                        "dog_name": p["dog_name"],
                        "model_prob": p["model_prob"],
                        "odds": p.get("odds", ""),
                        "overlay_pct": p.get("overlay_pct", ""),
                        "confidence": p.get("confidence", ""),
                        "bet_amount": p.get("bet_amount", ""),
                    }
                    for p in picks
                ]
            ).to_csv(csv_path, index=False)
        else:
            pd.DataFrame().to_csv(csv_path, index=False)

        output_paths = {"latest_json": latest_path, "picks_csv": csv_path}

    return {
        "run_date": date_str,
        "source": options.source,
        "venue_filter": options.venue,
        "dry_run": options.dry_run,
        "summary": {
            "venues": n_venues,
            "races": n_races,
            "runners": n_dogs if (n_dogs := len(features_df)) else 0,
            "bets": len(picks),
            "total_staked": float(sum(p.get("bet_amount", 0) for p in picks)),
        },
        "predictions": _prediction_records(predictions_df),
        "selected_bets": picks,
        "picks_json": picks_json,
        "outputs": output_paths,
        "meta": metadata,
    }
