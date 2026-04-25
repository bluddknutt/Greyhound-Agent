"""One-command live runner for the TAB pipeline.

Attempts sources in safe order and writes latest outputs:
  - latest_picks.json
  - latest_picks.csv

Usage:
  python run_live_pipeline.py
  python run_live_pipeline.py --date 2026-04-25 --csv-dir ./race_data/
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.bet_selector import format_picks_json
from src.tab_pipeline_service import PipelineOptions, resolve_date, run_pipeline

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live greyhound predictions with auto-fallback")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--venue", default=None)
    parser.add_argument("--csv-dir", default="./race_data/")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _write_empty_outputs(date_str: str, failed_attempts: list[dict]) -> dict:
    payload = format_picks_json([], date_str, source="none")
    payload["errors"] = failed_attempts

    latest_json = Path("latest_picks.json")
    latest_csv = Path("latest_picks.csv")

    latest_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    latest_csv.write_text("venue,race,box,dog_name,model_prob,odds,overlay_pct,confidence,bet_amount\n", encoding="utf-8")

    logger.warning("No source succeeded. Wrote empty outputs to %s and %s", latest_json, latest_csv)
    return {
        "ok": False,
        "source": "none",
        "run_date": date_str,
        "errors": failed_attempts,
        "outputs": {
            "latest_json": str(latest_json.resolve()),
            "latest_csv": str(latest_csv.resolve()),
        },
    }


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    date_str = resolve_date(args.date)
    failed_attempts = []

    for source in ("tab", "scrape", "csv"):
        options = PipelineOptions(
            source=source,
            date=date_str,
            venue=args.venue,
            csv_dir=args.csv_dir,
            dry_run=False,
        )
        try:
            logger.info("Attempting pipeline source=%s date=%s", source, date_str)
            result = run_pipeline(options)
            logger.info("Success with source=%s, bets=%d", source, result["summary"]["bets"])
            print(json.dumps({
                "ok": True,
                "source": source,
                "run_date": result["run_date"],
                "bets": result["summary"]["bets"],
                "outputs": result.get("outputs", {}),
                "skipped_races": result.get("meta", {}).get("skipped_races", []),
            }, indent=2, default=str))
            return 0
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            failed_attempts.append({"source": source, "error": msg})
            logger.warning("Source %s failed: %s", source, msg)

    summary = _write_empty_outputs(date_str, failed_attempts)
    print(json.dumps(summary, indent=2, default=str))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
