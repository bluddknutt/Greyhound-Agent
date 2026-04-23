"""
TAB Live Pipeline — multi-source greyhound prediction pipeline.

Sources:
  csv    — parse Expert Form CSVs from local directory
  tab    — fetch live data from TAB API (requires Australian IP)
  scrape — auto-download from thedogs.com.au Print Hub, then parse CSVs
"""

import argparse
import logging
import sys

from src.tab_pipeline_service import (
    DeployBlockedError,
    PipelineOptions,
    apply_composite_fallback,
    load_venue_models,
    predict_with_models,
    run_pipeline,
)


def _load_venue_models(venue_name):
    """Backwards-compatible wrapper for tests/imports."""
    return load_venue_models(venue_name)


def _apply_composite_fallback(features_df, mask):
    """Backwards-compatible wrapper for tests/imports."""
    return apply_composite_fallback(features_df, mask)


def _predict_with_models(features_df):
    """Backwards-compatible wrapper for tests/imports."""
    return predict_with_models(features_df)


def parse_args():
    parser = argparse.ArgumentParser(description="Greyhound TAB pipeline")
    parser.add_argument("--source", choices=["csv", "tab", "scrape"], default="csv")
    parser.add_argument("--csv-dir", default="./race_data/")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--venue", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _print_results(result: dict):
    print(f"\n{'='*60}")
    print(f"  Greyhound TAB Pipeline — {result['run_date']}")
    print(f"  Source: {result['source']}")
    print(f"{'='*60}")

    for race in result["predictions"]:
        print(f"\n  {race['venue']} R{race['race_number']}")
        print("  " + "─" * 50)
        print(f"  {'#':<4}{'Box':<5}{'Dog':<22}{'Prob':<8}{'Score':<8}")
        print("  " + "─" * 50)
        for runner in race["runners"]:
            dog = runner["dog_name"][:20]
            box = runner["box"] or 0
            print(f"  {runner['rank']:<4}{box:<5}{dog:<22}{runner['model_prob']:.3f}   {runner['final_score']:.2f}")

    picks = result["selected_bets"]
    if picks:
        print(f"\n{'='*60}")
        print(f"  SELECTED BETS ({len(picks)})")
        print(f"{'='*60}")
        for p in picks:
            odds_str = f"${p['odds']:.2f}" if p.get("odds") else "N/A"
            overlay_str = f"{p['overlay_pct']:.0f}%" if p.get("overlay_pct") is not None else "N/A"
            print(
                f"  BET: R{p['race_number']} {p['venue']} — BOX {p['box']} {p['dog_name']} | "
                f"prob={p['model_prob']:.1%} odds={odds_str} overlay={overlay_str} [{p.get('confidence', '')}]"
            )
    else:
        print("\n[pipeline] No value bets found")

    summary = result["summary"]
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"  Date:    {result['run_date']}")
    print(f"  Source:  {result['source']}")
    print(f"  Venues:  {summary['venues']}")
    print(f"  Races:   {summary['races']}")
    print(f"  Runners: {summary['runners']}")
    print(f"  Bets:    {summary['bets']}")
    if summary["total_staked"]:
        print(f"  Staked:  ${summary['total_staked']:.2f} AUD")
    print(f"{'='*60}\n")


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    options = PipelineOptions(
        source=args.source,
        date=args.date,
        venue=args.venue,
        csv_dir=args.csv_dir,
        dry_run=args.dry_run,
    )
    try:
        result = run_pipeline(options)
    except DeployBlockedError:
        sys.exit(1)
    _print_results(result)


if __name__ == "__main__":
    main()
