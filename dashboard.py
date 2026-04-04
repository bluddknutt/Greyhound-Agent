"""
dashboard.py — terminal P&L summary for greyhound predictions.

Usage:
    python dashboard.py           # show last 7 days + all-time
    python dashboard.py --days 30 # show last 30 days
    python dashboard.py --all     # all-time only
"""

import argparse
from src.results_tracker import get_summary


def _bar(value: float, max_abs: float = 50.0, width: int = 20) -> str:
    """Return a simple ASCII bar showing a P&L value."""
    if max_abs == 0:
        return " " * width
    ratio = min(abs(value) / max_abs, 1.0)
    filled = int(ratio * width)
    bar = ("+" if value >= 0 else "-") * filled
    return bar.ljust(width)


def _roi_label(roi: float) -> str:
    return f"{'+' if roi >= 0 else ''}{roi:.1f}%"


def print_summary(label: str, summary: dict) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print(f"{'═' * 60}")

    tb = summary["total_bets"]
    sb = summary["settled_bets"]
    wins = summary["win_count"]
    wr = summary["win_rate_pct"]
    roi = summary["roi_pct"]
    pl = summary["total_profit_loss"]
    streak = summary["current_streak"]
    stype = summary["streak_type"]

    print(f"  Total bets logged : {tb}")
    print(f"  Settled bets      : {sb}")
    print(f"  Wins              : {wins} ({wr:.1f}%)")
    pl_sign = "+" if pl >= 0 else ""
    print(f"  P&L               : {pl_sign}${pl:.2f}  (ROI {_roi_label(roi)})")

    if streak > 0 and stype != "none":
        streak_str = f"{streak} {stype}{'s' if streak != 1 else ''} in a row"
        print(f"  Current streak    : {streak_str}")
    else:
        print(f"  Current streak    : —")

    # ── Tier breakdown ─────────────────────────────────────
    by_tier = summary.get("by_tier", {})
    if by_tier:
        print(f"\n  {'Tier':<10} {'Bets':>5} {'Wins':>5} {'P&L':>10} {'ROI':>8}")
        print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*10} {'-'*8}")
        for tier in sorted(by_tier):
            t = by_tier[tier]
            pl_t = t["profit_loss"]
            sign = "+" if pl_t >= 0 else ""
            print(
                f"  {tier:<10} {t['bets']:>5} {t['wins']:>5} "
                f"  {sign}${pl_t:>7.2f} {_roi_label(t['roi_pct']):>8}"
            )

    # ── Meeting breakdown ───────────────────────────────────
    by_meeting = summary.get("by_meeting", {})
    if by_meeting:
        print(f"\n  {'Meeting':<22} {'Bets':>5} {'Wins':>5} {'P&L':>10}")
        print(f"  {'-'*22} {'-'*5} {'-'*5} {'-'*10}")
        sorted_meetings = sorted(
            by_meeting.items(), key=lambda kv: kv[1]["profit_loss"], reverse=True
        )
        for meeting, m in sorted_meetings:
            pl_m = m["profit_loss"]
            sign = "+" if pl_m >= 0 else ""
            print(
                f"  {meeting:<22} {m['bets']:>5} {m['wins']:>5}   {sign}${pl_m:>7.2f}"
            )

        # Best / worst
        best = sorted_meetings[0]
        worst = sorted_meetings[-1]
        if len(sorted_meetings) > 1:
            print(f"\n  Best meeting  : {best[0]}  (${best[1]['profit_loss']:+.2f})")
            print(f"  Worst meeting : {worst[0]}  (${worst[1]['profit_loss']:+.2f})")


def main():
    parser = argparse.ArgumentParser(description="Greyhound P&L dashboard")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=7, help="Show last N days (default 7)")
    group.add_argument("--all", action="store_true", dest="all_time", help="All-time only")
    args = parser.parse_args()

    if args.all_time:
        all_time = get_summary()
        print_summary("All-Time P&L", all_time)
    else:
        recent = get_summary(days=args.days)
        all_time = get_summary()
        print_summary(f"Last {args.days} Days", recent)
        print_summary("All-Time P&L", all_time)

    print(f"\n{'═' * 60}\n")


if __name__ == "__main__":
    main()
