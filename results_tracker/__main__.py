"""
results_tracker — minimal dashboard for greyhound prediction P&L.

Usage:
    python -m results_tracker dashboard
"""

import glob
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dashboard():
    # Latest picks file
    picks_files = sorted(glob.glob("outputs/picks*.csv"), reverse=True)
    if not picks_files:
        print("No picks found in outputs/ — run the pipeline first.")
        return

    picks = pd.read_csv(picks_files[0])
    print(f"\n=== Top Picks  [{picks_files[0]}] ===")

    # Handle both PDF-pipeline columns (Track/RaceNumber/DogName/FinalScore)
    # and CSV-pipeline columns (venue/race_number/dog_name/composite)
    col_map = {}
    if "venue" in picks.columns and "Track" not in picks.columns:
        col_map = {"venue": "Track", "race_number": "RaceNumber",
                   "dog_name": "DogName", "composite": "FinalScore"}
        picks = picks.rename(columns=col_map)

    display_cols = [c for c in ["Track", "RaceNumber", "Box", "DogName", "FinalScore"]
                    if c in picks.columns]
    print(picks[display_cols].head(20).to_string(index=False))

    # Latest results file for P&L
    result_files = sorted(glob.glob("outputs/results_*.csv"), reverse=True)
    if result_files:
        from scripts.fetch_results import compute_pnl
        results = pd.read_csv(result_files[0])
        pnl_df = compute_pnl(picks, results)
        if not pnl_df.empty:
            net = pnl_df["pnl"].sum()
            wins = int(pnl_df["correct"].sum())
            n = len(pnl_df)
            print(f"\n=== P&L Summary [{result_files[0]}] ===")
            print(pnl_df.to_string(index=False))
            print(f"\nNet: {net:+.2f} units  |  {wins}/{n} correct")
        else:
            print("\n(No matched races between picks and results)")
    else:
        print("\n(No results file found — re-run after races finish)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    if cmd == "dashboard":
        dashboard()
    else:
        print(f"Unknown command: {cmd}. Available: dashboard")
        sys.exit(1)
