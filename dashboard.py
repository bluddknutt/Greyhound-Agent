"""
dashboard.py — Terminal P&L summary for the greyhound prediction pipeline.

Prints:
  • Last 7 days P&L
  • All-time ROI
  • Best / worst meeting
  • Confidence tier breakdown
  • Current streak
"""

import sqlite3
import os
from datetime import datetime, timedelta
from results_tracker import _init_db, _connect, get_summary, DB_PATH


# ──────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────

def _settled_rows(db_path: str = DB_PATH) -> list[dict]:
    """Return all settled predictions as list of dicts."""
    _init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT race_id, meeting, race_number, date, dog_name,
                   predicted_rank, actual_result, odds_at_prediction,
                   stake, profit_loss, confidence_tier
            FROM predictions
            WHERE actual_result IS NOT NULL
            ORDER BY date ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _last_n_days(rows: list[dict], n: int) -> list[dict]:
    cutoff = (datetime.utcnow() - timedelta(days=n)).date()
    result = []
    for r in rows:
        try:
            row_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if row_date >= cutoff:
                result.append(r)
        except (ValueError, TypeError):
            pass
    return result


def _pl_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"bets": 0, "wins": 0, "profit_loss": 0.0, "staked": 0.0,
                "win_rate": 0.0, "roi_pct": 0.0}
    bets = len(rows)
    wins = sum(1 for r in rows if (r["profit_loss"] or 0) > 0)
    pl = sum(r["profit_loss"] or 0 for r in rows)
    staked = sum(r["stake"] for r in rows)
    return {
        "bets": bets,
        "wins": wins,
        "profit_loss": pl,
        "staked": staked,
        "win_rate": wins / bets,
        "roi_pct": pl / staked * 100 if staked > 0 else 0.0,
    }


def _meeting_breakdown(rows: list[dict]) -> list[dict]:
    """Aggregate P&L per meeting, sorted by net profit descending."""
    meetings: dict[str, dict] = {}
    for r in rows:
        m = r["meeting"]
        if m not in meetings:
            meetings[m] = {"meeting": m, "bets": 0, "wins": 0,
                           "profit_loss": 0.0, "staked": 0.0}
        meetings[m]["bets"] += 1
        if (r["profit_loss"] or 0) > 0:
            meetings[m]["wins"] += 1
        meetings[m]["profit_loss"] += r["profit_loss"] or 0
        meetings[m]["staked"] += r["stake"]

    result = []
    for stats in meetings.values():
        stats["roi_pct"] = (
            stats["profit_loss"] / stats["staked"] * 100
            if stats["staked"] > 0 else 0.0
        )
        result.append(stats)

    return sorted(result, key=lambda x: x["profit_loss"], reverse=True)


# ──────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────

def _pl_colour(value: float) -> str:
    """Return ANSI-coloured P&L string."""
    if value > 0:
        return f"\033[32m+${value:.2f}\033[0m"
    elif value < 0:
        return f"\033[31m-${abs(value):.2f}\033[0m"
    return f"$0.00"


def _roi_colour(value: float) -> str:
    if value > 0:
        return f"\033[32m+{value:.1f}%\033[0m"
    elif value < 0:
        return f"\033[31m{value:.1f}%\033[0m"
    return "0.0%"


def _streak_str(streak: int) -> str:
    if streak > 0:
        return f"\033[32m{streak}W streak\033[0m"
    elif streak < 0:
        return f"\033[31m{abs(streak)}L streak\033[0m"
    return "No streak"


def _bar(value: float, max_val: float, width: int = 20, char: str = "█") -> str:
    if max_val <= 0:
        return " " * width
    filled = int(round(min(value / max_val, 1.0) * width))
    return char * filled + "░" * (width - filled)


# ──────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────

def print_dashboard(db_path: str = DB_PATH) -> None:
    all_settled = _settled_rows(db_path)
    summary = get_summary(db_path)

    W = 60  # terminal width
    sep = "─" * W

    print()
    print("=" * W)
    print("  GREYHOUND PREDICTION DASHBOARD")
    print("=" * W)

    # ── All-time overview ──
    print()
    print("  ALL-TIME")
    print(f"  {sep}")
    total = summary["total_bets"]
    settled = summary["settled_bets"]
    print(f"  Total predictions : {total}  (settled: {settled})")
    if settled > 0:
        print(f"  Win rate          : {summary['win_rate']:.1%}")
        print(f"  Net P&L           : {_pl_colour(summary['total_profit_loss'])}")
        print(f"  Total staked      : ${summary['total_staked']:.2f}")
        print(f"  ROI               : {_roi_colour(summary['roi_pct'])}")
        print(f"  Streak            : {_streak_str(summary['streak'])}")
    else:
        print("  No settled predictions yet.")

    # ── Last 7 days ──
    last7 = _last_n_days(all_settled, 7)
    stats7 = _pl_stats(last7)
    print()
    print("  LAST 7 DAYS")
    print(f"  {sep}")
    if stats7["bets"] > 0:
        print(f"  Bets              : {stats7['bets']}")
        print(f"  Win rate          : {stats7['win_rate']:.1%}")
        print(f"  Net P&L           : {_pl_colour(stats7['profit_loss'])}")
        print(f"  ROI               : {_roi_colour(stats7['roi_pct'])}")
    else:
        print("  No settled predictions in the last 7 days.")

    # ── Confidence tier breakdown ──
    by_conf = summary.get("by_confidence", {})
    if by_conf:
        print()
        print("  CONFIDENCE TIER BREAKDOWN")
        print(f"  {sep}")
        tier_order = ["high", "medium", "low"]
        for tier in tier_order + [t for t in by_conf if t not in tier_order]:
            if tier not in by_conf:
                continue
            t = by_conf[tier]
            bar = _bar(max(0, t["win_rate"]), 1.0, width=15)
            print(
                f"  {tier.upper():<8} "
                f"{t['bets']:>4} bets  "
                f"WR {t['win_rate']:>5.1%}  [{bar}]  "
                f"{_pl_colour(t['profit_loss'])}"
            )

    # ── Best / worst meeting ──
    meeting_stats = _meeting_breakdown(all_settled)
    if meeting_stats:
        best = meeting_stats[0]
        worst = meeting_stats[-1]
        print()
        print("  MEETINGS")
        print(f"  {sep}")
        print(
            f"  Best  : {best['meeting']:<30} "
            f"{_pl_colour(best['profit_loss'])}  "
            f"ROI {_roi_colour(best['roi_pct'])}"
        )
        print(
            f"  Worst : {worst['meeting']:<30} "
            f"{_pl_colour(worst['profit_loss'])}  "
            f"ROI {_roi_colour(worst['roi_pct'])}"
        )

        if len(meeting_stats) > 2:
            print()
            print("  All meetings:")
            for stats in meeting_stats:
                indicator = "+" if stats["profit_loss"] >= 0 else "-"
                print(
                    f"    {indicator} {stats['meeting']:<28} "
                    f"{stats['bets']:>3} bets  "
                    f"{_pl_colour(stats['profit_loss'])}  "
                    f"ROI {_roi_colour(stats['roi_pct'])}"
                )

    print()
    print("=" * W)
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print greyhound prediction P&L dashboard.")
    parser.add_argument("--db", metavar="PATH", default=DB_PATH,
                        help=f"Path to SQLite database (default: {DB_PATH}).")
    args = parser.parse_args()
    print_dashboard(args.db)
