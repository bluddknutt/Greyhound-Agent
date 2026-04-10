"""
Greyhound Racing Pipeline — main entry point.

Orchestrates the full pipeline:
  1. Scrape detailed form from thedogs.com.au
  2. Score all runners with the 7-component composite engine
  3. Save picks CSV
  4. (Optional) Send HTML email report
  5. (Optional) Fetch actual results and compute P&L

Usage:
    python run_pipeline.py                         # run today, no email
    python run_pipeline.py --email                 # run today + send email
    python run_pipeline.py --all-races             # include all races (no cutoff)
    python run_pipeline.py --date 2026-04-10       # run for a specific date
    python run_pipeline.py --email-only            # send email from existing CSV
    python run_pipeline.py --track-results         # fetch results + compute P&L
    python run_pipeline.py --all-races --email     # full run with email
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd

# Ensure project root is on sys.path regardless of where the script is run from
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from src.config_loader import load_config
from src.scorer import predict, get_top4, print_predictions
from src.scrapers.scrape_detailed_form import scrape_all_detailed
from email_report import generate_html_report, send_or_save
from track_results import (
    fetch_all_results,
    compare_predictions,
    append_results_log,
    save_daily_summary,
    print_pnl_summary,
)

AEST = timezone(timedelta(hours=10))  # Australia/Brisbane — no DST

# Columns to include in the picks CSV output
_PICKS_COLUMNS = [
    "venue", "state", "race_number", "race_name", "race_time",
    "distance", "grade", "box", "dog_name", "trainer",
    "best_time", "last_4_starts", "composite", "win_prob",
    "implied_odds", "predicted_rank",
    "speed_score_norm", "form_score_norm", "box_bias_norm",
    "class_rating_norm", "early_speed_norm", "consistency_norm",
    "track_fitness_norm",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_today_aest() -> str:
    """Return today's date in YYYY-MM-DD format (AEST)."""
    return datetime.now(AEST).strftime("%Y-%m-%d")


def get_start_of_day_aest(date_str: str) -> datetime:
    """Return midnight AEST for the given date string."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=AEST)


def save_picks(top4: pd.DataFrame, date_str: str) -> str:
    """
    Save the top-4 picks to outputs/picks_{date}.csv.

    Parameters
    ----------
    top4 : pd.DataFrame
        Output of scorer.get_top4().
    date_str : str
        Date string for the filename.

    Returns
    -------
    str
        Path to the saved CSV file.
    """
    outputs_dir = os.path.join(_HERE, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    path = os.path.join(outputs_dir, f"picks_{date_str}.csv")

    cols = [c for c in _PICKS_COLUMNS if c in top4.columns]
    top4[cols].to_csv(path, index=False)
    print(f"[pipeline] Picks saved to {path}  ({len(top4)} rows)")
    return path


def load_existing_picks(date_str: str) -> pd.DataFrame:
    """Load outputs/picks_{date}.csv, raise FileNotFoundError if missing."""
    path = os.path.join(_HERE, "outputs", f"picks_{date_str}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Picks file not found: {path}\n"
            f"Run 'python run_pipeline.py --date {date_str}' first."
        )
    return pd.read_csv(path)


def load_existing_detailed(date_str: str) -> pd.DataFrame:
    """Load outputs/detailed_form_{date}.csv; return empty DF if missing."""
    path = os.path.join(_HERE, "outputs", f"detailed_form_{date_str}.csv")
    if not os.path.exists(path):
        print(f"[pipeline] WARNING: detailed_form CSV not found at {path}")
        return pd.DataFrame()
    return pd.read_csv(path)


# ──────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Greyhound racing prediction pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date to run (default: today AEST).",
    )
    parser.add_argument(
        "--all-races",
        action="store_true",
        help="Include all races on the day (skip upcoming-only cutoff).",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Send HTML email report after scoring (falls back to file save).",
    )
    parser.add_argument(
        "--email-only",
        action="store_true",
        dest="email_only",
        help="Load existing picks CSV and send email report (skip scrape/score).",
    )
    parser.add_argument(
        "--track-results",
        action="store_true",
        dest="track_results",
        help="Fetch actual race results and compute P&L after scoring.",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Orchestrate the full pipeline according to CLI flags."""
    args = parse_args()
    config = load_config()

    date_str = args.date or get_today_aest()
    print(f"\n{'='*60}")
    print(f"  Greyhound Pipeline — {date_str}")
    print(f"{'='*60}\n")

    # ── Email-only mode ──────────────────────────────────────────────────────
    if args.email_only:
        print("[pipeline] Email-only mode: loading existing picks ...")
        try:
            top4 = load_existing_picks(date_str)
            df = load_existing_detailed(date_str)
        except FileNotFoundError as exc:
            print(f"[pipeline] ERROR: {exc}")
            sys.exit(1)

        html = generate_html_report(df, top4, date_str)
        path = send_or_save(html, date_str, config)
        if path:
            print(f"[pipeline] Email failed — report saved at {path}")
        return

    # ── Step 1: Scrape ───────────────────────────────────────────────────────
    if args.all_races:
        cutoff_time = get_start_of_day_aest(date_str)
        print(f"[pipeline] Scraping ALL races on {date_str} (no cutoff) ...")
    else:
        cutoff_time = datetime.now(AEST)
        print(f"[pipeline] Scraping upcoming races from {cutoff_time.strftime('%H:%M')} AEST ...")

    runners = scrape_all_detailed(date_str, cutoff_time)

    if not runners:
        print("[pipeline] WARNING: No runners found. Check the date or try --all-races.")
        sys.exit(0)

    # Save detailed form CSV (scrape_all_detailed returns data but doesn't save)
    outputs_dir = os.path.join(_HERE, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    detailed_path = os.path.join(outputs_dir, f"detailed_form_{date_str}.csv")
    df_raw = pd.DataFrame(runners)
    df_raw.to_csv(detailed_path, index=False)
    print(f"[pipeline] Detailed form saved to {detailed_path}  ({len(df_raw)} rows)")

    # ── Step 2: Score ────────────────────────────────────────────────────────
    print("\n[pipeline] Scoring runners ...")
    try:
        df = predict(detailed_path)
    except Exception as exc:
        print(f"[pipeline] ERROR during scoring: {exc}")
        sys.exit(1)

    top4 = get_top4(df)
    print_predictions(top4, df)

    # ── Step 3: Save picks ───────────────────────────────────────────────────
    save_picks(top4, date_str)

    # ── Step 4: Email ────────────────────────────────────────────────────────
    if args.email:
        print("\n[pipeline] Generating email report ...")
        html = generate_html_report(df, top4, date_str)
        path = send_or_save(html, date_str, config)
        if path:
            print(f"[pipeline] Email failed — report saved at {path}")

    # ── Step 5: Track results ────────────────────────────────────────────────
    if args.track_results:
        print("\n[pipeline] Fetching actual race results ...")
        venues = df["venue"].dropna().unique().tolist()
        results_df = fetch_all_results(date_str, venues)

        if results_df.empty:
            print("[pipeline] No results available yet — races may still be running.")
        else:
            bet_amount = float(config.get("tracking", {}).get("bet_amount", 10.0))
            metrics = compare_predictions(top4, results_df, bet_amount=bet_amount)
            print_pnl_summary(metrics)
            append_results_log(metrics, date_str)
            save_daily_summary(metrics, date_str)

    print(f"\n[pipeline] Done.\n")


if __name__ == "__main__":
    main()
