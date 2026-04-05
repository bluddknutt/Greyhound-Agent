"""
Fetch today's official race results from FastTrack GRV API (+ TAB API stub),
update the SQLite results table, and print a daily P&L summary.

Bet model (per pick):
  - "win"   bet: +$8 net profit if finishes 1st, -$1 otherwise
  - "place" bet: +$2 net profit if finishes 1st/2nd/3rd, -$1 otherwise
  - "watch" bets are tracked but not included in P&L

Usage:
  python3 scripts/fetch_results.py
  python3 scripts/fetch_results.py --date 2026-04-05
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
# FastTrack uses bare `import mapping` so add src/data to path
sys.path.insert(0, str(REPO_ROOT / "src" / "data"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

AEST = timezone(timedelta(hours=10))


# ---------------------------------------------------------------------------
# Source 1: FastTrack GRV API
# ---------------------------------------------------------------------------
def fetch_via_fasttrack(date_str: str) -> list:
    """
    Fetch race results from the FastTrack GRV API.
    Returns a list of dicts: {track, race_number, box, dog_name, finish_position, win_time}
    """
    ft_key = os.environ.get("FAST_TRACK_API_KEY", "")
    if not ft_key or ft_key == "your_fasttrack_key_here":
        print("[FastTrack] No FAST_TRACK_API_KEY configured — skipping FastTrack fetch.")
        return []

    print(f"[FastTrack] Fetching results for {date_str}...")
    try:
        from fasttrack import Fasttrack  # noqa: E402  (src/data/fasttrack.py)
        ft = Fasttrack(ft_key)
        races_df, dogs_df = ft.getRaceResults(date_str, date_str)
    except Exception as exc:
        print(f"[FastTrack] ERROR fetching results: {exc}")
        return []

    if dogs_df is None or dogs_df.empty:
        print("[FastTrack] No dog results returned.")
        return []

    results = []
    for _, row in dogs_df.iterrows():
        # Map FastTrack columns to our schema
        # Column names come from the XML: @box, Name, Placing, RunTime, RaceId, Track, date
        try:
            placing_raw = str(row.get("Placing", "")).strip()
            finish_pos = int(placing_raw) if placing_raw.isdigit() else None
            run_time_raw = row.get("RunTime", None)
            win_time = float(run_time_raw) if run_time_raw not in (None, "", "None") else None
            results.append({
                "track": str(row.get("Track", "")),
                "race_number": str(row.get("RaceId", "")),  # may need parsing
                "box": int(row["@box"]) if "@box" in row and str(row["@box"]).isdigit() else None,
                "dog_name": str(row.get("Name", "")),
                "finish_position": finish_pos,
                "win_time": win_time,
            })
        except Exception as exc:
            print(f"  WARN: could not parse result row: {exc}")

    print(f"[FastTrack] Retrieved {len(results)} dog results.")
    return results


# ---------------------------------------------------------------------------
# Source 2: TAB API stub
# ---------------------------------------------------------------------------
def fetch_via_tab_api(date_str: str) -> list:
    """
    TAB API results stub.

    Replace this function body with real TAB API calls once you have access.

    Expected return: list of dicts with keys:
      track, race_number, box, dog_name, finish_position, win_time
    """
    tab_key = os.environ.get("TAB_API_KEY", "")
    if not tab_key or tab_key == "your_tab_api_key_here":
        print("[TAB API] No TAB_API_KEY configured — skipping TAB results fetch.")
        return []

    print(f"[TAB API] TAB_API_KEY found — attempting results fetch for {date_str}...")

    # --- Replace everything below this line with real TAB API calls ---
    # Example structure (pseudo-code):
    #
    # import requests
    # BASE = "https://api.tab.com.au/v1"
    # headers = {"Authorization": f"Bearer {tab_key}"}
    # resp = requests.get(f"{BASE}/racing/dates/{date_str}/results", headers=headers, timeout=30)
    # resp.raise_for_status()
    # meetings = resp.json()["meetings"]
    # results = []
    # for meeting in meetings:
    #     for race in meeting["races"]:
    #         for runner in race["results"]:
    #             results.append({
    #                 "track": meeting["venueName"],
    #                 "race_number": race["raceNumber"],
    #                 "box": runner["barrierNumber"],
    #                 "dog_name": runner["runnerName"],
    #                 "finish_position": runner["finishingPosition"],
    #                 "win_time": runner.get("runTime"),
    #             })
    # return results

    print("[TAB API] STUB: Real TAB API results call not yet implemented. Returning empty list.")
    return []


# ---------------------------------------------------------------------------
# SQLite update
# ---------------------------------------------------------------------------
def save_results(results: list, date_str: str, conn) -> int:
    """Upsert results into the results table. Returns count saved."""
    saved = 0
    for r in results:
        try:
            conn.execute(
                """
                INSERT INTO results
                    (race_date, track, race_number, box, dog_name, finish_position, win_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(race_date, track, race_number, box)
                DO UPDATE SET
                    dog_name        = excluded.dog_name,
                    finish_position = excluded.finish_position,
                    win_time        = excluded.win_time,
                    created_at      = datetime('now','localtime')
                """,
                (
                    date_str,
                    r["track"],
                    str(r["race_number"]),
                    r["box"],
                    r["dog_name"],
                    r["finish_position"],
                    r["win_time"],
                ),
            )
            saved += 1
        except Exception as exc:
            print(f"  WARN: could not save result {r}: {exc}")
    conn.commit()
    return saved


# ---------------------------------------------------------------------------
# P&L calculation
# ---------------------------------------------------------------------------
def compute_pnl(date_str: str, conn) -> dict:
    """
    Join predictions ↔ results for date_str and compute P&L.
    Returns a summary dict.
    """
    rows = conn.execute(
        """
        SELECT
            p.track, p.race_number, p.box, p.dog_name,
            p.final_score, p.bet_type,
            r.finish_position
        FROM predictions p
        LEFT JOIN results r
            ON  p.race_date   = r.race_date
            AND p.track       = r.track
            AND p.race_number = CAST(r.race_number AS TEXT)
            AND p.box         = r.box
        WHERE p.race_date = ?
          AND p.bet_type IN ('win', 'place')
        """,
        (date_str,),
    ).fetchall()

    total_picks = len(rows)
    wins = 0
    places = 0
    profit_loss = 0.0
    unresolved = 0

    for track, race_num, box, dog, score, bet_type, finish_pos in rows:
        if finish_pos is None:
            unresolved += 1
            continue

        if bet_type == "win":
            if finish_pos == 1:
                wins += 1
                profit_loss += 8.0   # net profit on $1 win bet at approx $9
            else:
                profit_loss -= 1.0
        elif bet_type == "place":
            if finish_pos <= 3:
                places += 1
                profit_loss += 2.0   # net profit on $1 place bet at approx $3
            else:
                profit_loss -= 1.0

    return {
        "race_date": date_str,
        "total_picks": total_picks,
        "wins": wins,
        "places": places,
        "profit_loss": round(profit_loss, 2),
        "unresolved": unresolved,
    }


def print_pnl_summary(summary: dict):
    pnl = summary["profit_loss"]
    sign = "+" if pnl >= 0 else ""
    print()
    print("=" * 50)
    print(f"  DAILY P&L SUMMARY — {summary['race_date']}")
    print("=" * 50)
    print(f"  Total picks  : {summary['total_picks']}")
    print(f"  Wins         : {summary['wins']}")
    print(f"  Places       : {summary['places']}")
    print(f"  Unresolved   : {summary['unresolved']}")
    print(f"  Profit/Loss  : {sign}${pnl:.2f}")
    print("=" * 50)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch results and compute daily P&L")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today AEST)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(AEST).strftime("%Y-%m-%d")
    print(f"=== fetch_results.py | date={date_str} ===")

    from scripts.init_db import init_db
    conn = init_db()

    # Fetch from all sources and merge (deduplicate by track+race+box)
    all_results: dict[tuple, dict] = {}

    for result in fetch_via_fasttrack(date_str):
        key = (result["track"], str(result["race_number"]), result["box"])
        all_results[key] = result

    for result in fetch_via_tab_api(date_str):
        key = (result["track"], str(result["race_number"]), result["box"])
        if key not in all_results:
            all_results[key] = result

    results_list = list(all_results.values())
    print(f"Total unique results: {len(results_list)}")

    saved = save_results(results_list, date_str, conn)
    print(f"Saved {saved} results to SQLite.")

    summary = compute_pnl(date_str, conn)

    # Persist P&L summary
    try:
        conn.execute(
            """
            INSERT INTO pnl_log (race_date, total_picks, wins, places, profit_loss)
            VALUES (:race_date, :total_picks, :wins, :places, :profit_loss)
            ON CONFLICT(race_date)
            DO UPDATE SET
                total_picks = excluded.total_picks,
                wins        = excluded.wins,
                places      = excluded.places,
                profit_loss = excluded.profit_loss,
                logged_at   = datetime('now','localtime')
            """,
            summary,
        )
        conn.commit()
    except Exception as exc:
        print(f"WARN: could not save P&L log: {exc}")

    conn.close()
    print_pnl_summary(summary)
    print(f"=== fetch_results.py complete ===")


if __name__ == "__main__":
    main()
