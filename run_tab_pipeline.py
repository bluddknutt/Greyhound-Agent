"""
TAB Live Pipeline — multi-source greyhound prediction pipeline.

Sources:
  csv    — parse Expert Form CSVs from local directory
  tab    — fetch live data from TAB API (requires Australian IP)
  scrape — auto-download from thedogs.com.au Print Hub, then parse CSVs

Pipeline steps:
  1. Ingest data (csv/tab/scrape)
  2. Engineer 74 features
  3. Run pkl model inference (3 venues) with composite fallback
  4. Select value bets
  5. Write latest_picks.json + tab_picks_{date}.csv

Usage:
  python run_tab_pipeline.py
  python run_tab_pipeline.py --source csv --csv-dir ./race_data/
  python run_tab_pipeline.py --source tab --date 2026-04-11
  python run_tab_pipeline.py --source scrape --date 2026-04-11
  python run_tab_pipeline.py --dry-run
  python run_tab_pipeline.py --venue HEA --verbose
"""

import argparse
import json
import logging
import os
import pickle
import sys
import warnings
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

# Ensure project root is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from src.config_loader import load_config
from src.data.csv_ingest import load_meeting_csvs
from src.data.tab_api import fetch_all_races, VENUE_MNEMONIC_TO_MODEL
from src.tab_feature_engineer import engineer_features, MODEL_FEATURES
from src.bet_selector import select_bets, format_picks_json
from src.scrapers.thedogs_scraper import scrape_print_hub

AEST = timezone(timedelta(hours=10))

# Venue name → pkl model prefix mapping
# The pkl files in the project root use these exact names:
#   "Angle Park_gb.pkl", "BALLARAT_rf.pkl", etc.
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


def _load_venue_models(venue_name):
    """
    Load pkl models for a venue.

    Returns (gb_model, rf_model, scaler) or None if not available.
    """
    model_prefix = VENUE_MODEL_NAMES.get(venue_name)
    if not model_prefix:
        # Try case-insensitive match
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

        # Verify feature alignment
        if hasattr(scaler, "feature_names_in_"):
            expected = list(scaler.feature_names_in_)
            if expected != MODEL_FEATURES:
                mismatched = set(expected) ^ set(MODEL_FEATURES)
                print(f"  WARNING: Feature mismatch for {model_prefix}: {mismatched}")

        return gb, rf, scaler

    except Exception as e:
        print(f"  ERROR: Failed to load models for {model_prefix}: {e}")
        return None


def _predict_with_models(features_df):
    """
    Run pkl model inference on features DataFrame.

    For venues with models: scale features → run GB + RF → ensemble average.
    For venues without models: normalize FinalScore within race as fallback.

    Adds 'model_prob' column to the DataFrame.
    """
    features_df = features_df.copy()
    features_df["model_prob"] = np.nan

    venues = features_df["_venue"].unique()

    for venue in venues:
        venue_mask = features_df["_venue"] == venue
        venue_df = features_df.loc[venue_mask]

        models = _load_venue_models(venue)

        if models:
            gb, rf, scaler = models
            print(f"  {venue}: Using pkl models (GB + RF ensemble)")

            try:
                X = venue_df[MODEL_FEATURES].values
                X_scaled = scaler.transform(X)

                gb_probs = gb.predict_proba(X_scaled)[:, 1]
                rf_probs = rf.predict_proba(X_scaled)[:, 1]
                ensemble_probs = (gb_probs + rf_probs) / 2

                features_df.loc[venue_mask, "model_prob"] = ensemble_probs

            except Exception as e:
                print(f"  ERROR: Model inference failed for {venue}: {e}")
                print(f"  Falling back to composite scoring for {venue}")
                _apply_composite_fallback(features_df, venue_mask)
        else:
            print(f"  {venue}: No pkl model — using composite fallback")
            _apply_composite_fallback(features_df, venue_mask)

    return features_df


def _apply_composite_fallback(features_df, mask):
    """
    Apply composite scoring fallback: normalise FinalScore within each
    race to produce model_prob (same approach as scorer.py).
    """
    venue_df = features_df.loc[mask]

    for _, race_group in venue_df.groupby("_race_number"):
        idx = race_group.index
        scores = race_group["FinalScore"]
        total = scores.sum()
        if total > 0:
            features_df.loc[idx, "model_prob"] = scores / total
        else:
            features_df.loc[idx, "model_prob"] = 1.0 / len(race_group)


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Greyhound racing prediction pipeline (TAB/CSV/Scrape)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["csv", "tab", "scrape"],
        default="csv",
        help="Data source (default: csv)",
    )
    parser.add_argument(
        "--csv-dir",
        default="./race_data/",
        help="Directory containing Race CSVs (default: ./race_data/)",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date to run (default: today AEST)",
    )
    parser.add_argument(
        "--venue",
        default=None,
        help="Filter to a specific venue (case-insensitive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without writing output files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main():
    """Run the full TAB pipeline."""
    args = parse_args()
    config = load_config()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    date_str = args.date or datetime.now(AEST).strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  Greyhound TAB Pipeline — {date_str}")
    print(f"  Source: {args.source}")
    print(f"{'='*60}\n")

    # ── Step 0 (scrape mode): Download from Print Hub ────────────────
    csv_dir = args.csv_dir
    if args.source == "scrape":
        print("[pipeline] Scraping Print Hub for race data...")
        download_dir = config.get("scraper", {}).get("download_dir", "./downloads/")
        results = scrape_print_hub(date_str, download_dir, args.venue)

        if not results:
            print("[pipeline] ERROR: No files downloaded from Print Hub")
            sys.exit(1)

        # Find directories with expert_form.csv files
        csv_dir = os.path.join(download_dir, date_str)
        n_csvs = sum(
            1 for v in results.values()
            if "expert_form_csv" in v
        )
        print(f"[pipeline] Downloaded {n_csvs} Expert Form CSVs")

    # ── Step 1: Ingest data ──────────────────────────────────────────
    print(f"[pipeline] Loading data (source={args.source})...")

    if args.source in ("csv", "scrape"):
        raw_df = load_meeting_csvs(csv_dir, venue=args.venue)
        if raw_df.empty:
            print(f"[pipeline] ERROR: No race data found in {csv_dir}")
            print(f"  Looking for files matching: Race_*.csv")
            sys.exit(1)
    elif args.source == "tab":
        raw_df = fetch_all_races(date_str)
        if raw_df.empty:
            print("[pipeline] ERROR: No data from TAB API.")
            print("  Check: Australian IP required, date format YYYY-MM-DD")
            sys.exit(1)
        if args.venue:
            raw_df = raw_df[
                raw_df["venue"].str.lower().str.contains(args.venue.lower())
                | raw_df["track"].str.lower().str.contains(args.venue.lower())
            ]

    n_runners = len(raw_df)
    n_venues = raw_df["venue"].nunique() if "venue" in raw_df.columns else 0
    n_races = raw_df.groupby(["venue", "race_number"]).ngroups if not raw_df.empty else 0
    print(f"[pipeline] Loaded {n_runners} form lines across {n_venues} venues, {n_races} races")

    # ── Step 2: Engineer features ────────────────────────────────────
    print("\n[pipeline] Engineering 74 features...")
    features_df = engineer_features(raw_df)

    if features_df.empty:
        print("[pipeline] ERROR: Feature engineering produced no output")
        sys.exit(1)

    n_dogs = len(features_df)
    print(f"[pipeline] Engineered {n_dogs} runner feature vectors ({len(MODEL_FEATURES)} features)")

    # ── Step 3: Model inference ──────────────────────────────────────
    print("\n[pipeline] Running model inference...")
    predictions_df = _predict_with_models(features_df)

    # ── Step 4: Select bets ──────────────────────────────────────────
    print("\n[pipeline] Selecting value bets...")
    picks = select_bets(predictions_df, config)

    # ── Print predictions ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  PREDICTIONS — {date_str}")
    print(f"{'='*60}")

    for (venue, race_num), race_df in predictions_df.groupby(["_venue", "_race_number"]):
        race_df = race_df.sort_values("model_prob", ascending=False)
        print(f"\n  {venue} R{int(race_num)}")
        print(f"  {'─'*50}")
        print(f"  {'#':<4}{'Box':<5}{'Dog':<22}{'Prob':<8}{'Score':<8}")
        print(f"  {'─'*50}")

        for rank, (_, r) in enumerate(race_df.iterrows(), 1):
            dog = str(r.get("_dog_name", ""))[:20]
            box = int(r.get("_dog_number", 0)) if pd.notna(r.get("_dog_number")) else 0
            prob = r.get("model_prob", 0)
            score = r.get("FinalScore", 0)
            print(f"  {rank:<4}{box:<5}{dog:<22}{prob:.3f}   {score:.2f}")

    # Print selected bets
    if picks:
        print(f"\n{'='*60}")
        print(f"  SELECTED BETS ({len(picks)})")
        print(f"{'='*60}")
        for p in picks:
            odds_str = f"${p['odds']:.2f}" if p.get("odds") else "N/A"
            overlay_str = f"{p['overlay_pct']:.0f}%" if p.get("overlay_pct") is not None else "N/A"
            print(
                f"  BET: R{p['race_number']} {p['venue']} — "
                f"BOX {p['box']} {p['dog_name']} | "
                f"prob={p['model_prob']:.1%} odds={odds_str} "
                f"overlay={overlay_str} [{p.get('confidence', '')}]"
            )
    else:
        print(f"\n[pipeline] No value bets found for {date_str}")

    # ── Step 5: Write output ─────────────────────────────────────────
    if not args.dry_run:
        outputs_dir = os.path.join(_HERE, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        # Write latest_picks.json
        picks_json = format_picks_json(picks, date_str, source=args.source)
        json_path = os.path.join(_HERE, "latest_picks.json")
        with open(json_path, "w") as f:
            json.dump(picks_json, f, indent=2, default=str)
        print(f"\n[pipeline] Saved {json_path}")

        # Write tab_picks_{date}.csv
        csv_path = os.path.join(outputs_dir, f"tab_picks_{date_str}.csv")
        if picks:
            picks_flat = []
            for p in picks:
                picks_flat.append({
                    "venue": p["venue"],
                    "race": p["race_number"],
                    "box": p["box"],
                    "dog_name": p["dog_name"],
                    "model_prob": p["model_prob"],
                    "odds": p.get("odds", ""),
                    "overlay_pct": p.get("overlay_pct", ""),
                    "confidence": p.get("confidence", ""),
                    "bet_amount": p.get("bet_amount", ""),
                })
            pd.DataFrame(picks_flat).to_csv(csv_path, index=False)
        else:
            pd.DataFrame().to_csv(csv_path, index=False)
        print(f"[pipeline] Saved {csv_path}")
    else:
        print("\n[pipeline] Dry run — no files written")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Date:    {date_str}")
    print(f"  Source:  {args.source}")
    print(f"  Venues:  {n_venues}")
    print(f"  Races:   {n_races}")
    print(f"  Runners: {n_dogs}")
    print(f"  Bets:    {len(picks)}")
    if picks:
        total_staked = sum(p.get("bet_amount", 0) for p in picks)
        print(f"  Staked:  ${total_staked:.2f} AUD")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
