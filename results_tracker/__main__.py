"""
results_tracker — minimal dashboard for reviewing picks and P&L.

Usage:
    python -m results_tracker dashboard
"""

import glob
import os
import sys

import pandas as pd

# Ensure project root is on path so scripts.fetch_results is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dashboard():
    # Load the most recent picks file
    picks_files = sorted(glob.glob("outputs/picks*.csv"), reverse=True)
    if not picks_files:
        print("No picks found in outputs/  — run the pipeline first.")
        return

    picks = pd.read_csv(picks_files[0])
    print(f"\n=== Top Picks  ({picks_files[0]}) ===")

    # Handle both PDF-pipeline columns (Track/RaceNumber) and CSV-pipeline columns (venue/race_number)
    if "Track" in picks.columns:
        cols = [c for c in ["Track", "RaceNumber", "Box", "DogName", "FinalScore"] if c in picks.columns]
    else:
        cols = [c for c in ["venue", "race_number", "box", "dog_name", "composite", "win_prob"] if c in picks.columns]

    print(picks[cols].head(20).to_string(index=False))

    # Load most recent results file for P&L
    result_files = sorted(glob.glob("outputs/results_*.csv"), reverse=True)
    if not result_files:
        print("\n(No results file found — run fetch_results.py after races finish)")
        return

    from scripts.fetch_results import compute_pnl

    results = pd.read_csv(result_files[0])
    pnl_df = compute_pnl(picks, results)

    if pnl_df.empty:
        print("\n(No picks matched today's results)")
        return

    net = pnl_df["pnl"].sum()
    wins = int(pnl_df["correct"].sum())
    n = len(pnl_df)

    print(f"\n=== P&L Summary  ({result_files[0]}) ===")
    print(pnl_df.to_string(index=False))
    print(f"\nNet: {net:+.2f} units  |  {wins}/{n} correct ({wins/n:.0%})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    if cmd == "dashboard":
        dashboard()
    else:
        print(f"Unknown command: {cmd}. Available: dashboard")
        sys.exit(1)
