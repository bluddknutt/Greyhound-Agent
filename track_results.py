"""
Results tracking and P&L calculator for the Greyhound prediction pipeline.

After races complete, this module:
  1. Scrapes actual race results from thedogs.com.au
  2. Compares predictions (picks_{date}.csv) vs actual finishing positions
  3. Computes hit rate, place rate, top-4 accuracy, and flat-bet P&L
  4. Appends rows to outputs/results_log.csv and outputs/daily_summary.csv

Usage:
    python track_results.py --date 2026-04-10

Public API (also importable):
    fetch_all_results(date_str, venue_slugs)  -> pd.DataFrame
    compare_predictions(picks_df, results_df) -> dict
    append_results_log(metrics, date_str)     -> None
    save_daily_summary(metrics, date_str)     -> None
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd
import requests

AEST = timezone(timedelta(hours=10))  # Australia/Brisbane — no DST
BASE_URL = "https://www.thedogs.com.au"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}
REQUEST_DELAY = 0.3  # seconds between requests

# ──────────────────────────────────────────────────────────────────────────────
# Track name helpers  (reuses logic from scripts/fetch_results.py)
# ──────────────────────────────────────────────────────────────────────────────

def _venue_name_to_slug(name: str) -> str:
    """Best-effort conversion of a venue full name to its URL slug."""
    return name.lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")


def _normalise_name(name: str) -> str:
    """Lower-case and strip for fuzzy matching."""
    return name.lower().strip()


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────────────────────────────────────

def _fetch(url: str, retries: int = 3) -> str | None:
    """Fetch a URL with retry logic. Returns HTML or None on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  WARN: Failed to fetch {url}: {exc}")
                return None
            time.sleep(1)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Scrape venue slugs for a given date
# ──────────────────────────────────────────────────────────────────────────────

def get_venue_slugs(date_str: str) -> dict[str, str]:
    """
    Scrape thedogs.com.au/racing to get venue name → slug mapping for a date.

    Returns
    -------
    dict
        Maps canonical venue name (str) → URL slug (str).
    """
    html = _fetch(f"{BASE_URL}/racing")
    if not html:
        return {}
    pattern = (
        r'meetings-venues__name">'
        r'<a[^>]*href="(/racing/([^/]+)/'
        + re.escape(date_str)
        + r'\?trial=false)">([^<]+)</a>'
    )
    matches = re.findall(pattern, html)
    result: dict[str, str] = {}
    for _path, slug, name in matches:
        result[name.strip()] = slug
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Scrape results for a single race
# ──────────────────────────────────────────────────────────────────────────────

def fetch_race_result(
    venue_slug: str,
    date_str: str,
    race_number: int,
) -> dict[str, Any] | None:
    """
    Scrape the result of one completed race.

    Looks for the finishing-position order in the race result table.
    The first runner listed (by finishing position) is the winner.

    Parameters
    ----------
    venue_slug : str
        URL slug for the venue (e.g. "albion-park").
    date_str : str
        Date in YYYY-MM-DD format.
    race_number : int
        Race number within the meeting.

    Returns
    -------
    dict | None
        {'venue_slug', 'race_number', 'winner', 'finishing_order': [str, ...]}
        or None if the result is not yet available / parse failed.
    """
    # Try race-specific URL pattern first
    race_url = f"{BASE_URL}/racing/{venue_slug}/{date_str}/race-{race_number}?trial=false"
    html = _fetch(race_url)
    if not html:
        return None

    # Detect if the race has results: look for "result" class markers
    # thedogs.com.au result tables have rows with placing numbers
    # Strategy 1: look for finished placing rows with dog name links
    finishing_order = []

    # Pattern for result rows — dog name appears as link text in result tables
    # <td class="...">1</td> ... <a href="/dogs/{id}/{slug}">DogName</a>
    # Try to extract rows with a numeric placing + dog name
    result_row_pattern = re.compile(
        r'<td[^>]*>(\d+)</td>.*?href="/dogs/\d+/[^"]+">([^<]+)</a>',
        re.DOTALL,
    )
    matches = result_row_pattern.findall(html)

    if matches:
        # Sort by placing number and extract dog names
        sorted_matches = sorted(matches, key=lambda x: int(x[0]))
        finishing_order = [m[1].strip() for m in sorted_matches]
    else:
        # Fallback: extract dog name links in document order (first = winner in result tables)
        fallback_pattern = re.compile(r'href="/dogs/\d+/[^"]+">([^<]+)</a>')
        candidates = fallback_pattern.findall(html)
        # Filter out non-dog-name candidates (nav links etc.) — take first few unique names
        seen: set[str] = set()
        for name in candidates:
            clean = name.strip()
            if clean and len(clean) > 2 and clean not in seen:
                seen.add(clean)
                finishing_order.append(clean)
                if len(finishing_order) >= 8:
                    break

    if not finishing_order:
        return None  # Race not yet complete or parse failed

    return {
        "venue_slug": venue_slug,
        "race_number": race_number,
        "winner": finishing_order[0],
        "finishing_order": finishing_order,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Scrape all results for a date
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_results(
    date_str: str,
    venues: list[str],
) -> pd.DataFrame:
    """
    Fetch actual race results for all venues on a given date.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.
    venues : list[str]
        List of venue full names (from picks CSV).

    Returns
    -------
    pd.DataFrame
        Columns: venue, venue_slug, race_number, winner, finishing_order
    """
    print(f"\n[track_results] Fetching results for {date_str} ...")

    # Get slug mapping from the site
    slug_map = get_venue_slugs(date_str)

    rows = []
    for venue_name in venues:
        # Find slug: try direct lookup, then best-effort derivation
        slug = slug_map.get(venue_name)
        if not slug:
            # Try case-insensitive match
            for k, v in slug_map.items():
                if _normalise_name(k) == _normalise_name(venue_name):
                    slug = v
                    break
        if not slug:
            # Fallback: derive from name
            slug = _venue_name_to_slug(venue_name)
            print(f"  WARN: No slug found for '{venue_name}', using derived slug '{slug}'")

        # Fetch all races at this venue (up to 12)
        for race_num in range(1, 13):
            result = fetch_race_result(slug, date_str, race_num)
            if result is None:
                # Either no more races or not yet complete — stop for this venue
                break
            rows.append({
                "venue": venue_name,
                "venue_slug": slug,
                "race_number": race_num,
                "winner": result["winner"],
                "finishing_order": "|".join(result["finishing_order"]),
            })
            time.sleep(REQUEST_DELAY)

    df = pd.DataFrame(rows)
    if not df.empty:
        print(f"[track_results] Fetched {len(df)} race results across {df['venue'].nunique()} venues.")
    else:
        print("[track_results] No completed results found.")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Compare predictions vs results
# ──────────────────────────────────────────────────────────────────────────────

def compare_predictions(
    picks_df: pd.DataFrame,
    results_df: pd.DataFrame,
    bet_amount: float = 10.0,
) -> dict[str, Any]:
    """
    Compare picks against actual results and compute P&L metrics.

    Parameters
    ----------
    picks_df : pd.DataFrame
        Top-4 picks per race.  Required columns:
        venue, race_number, dog_name, composite, win_prob,
        implied_odds, predicted_rank
    results_df : pd.DataFrame
        Actual results.  Required columns: venue, race_number, winner
    bet_amount : float
        Flat stake per race for simulated P&L (default $10).

    Returns
    -------
    dict with keys:
        top_pick_hit_rate    float  — top pick was winner
        top_pick_place_rate  float  — top pick finished in finishing_order[:3]
        top4_accuracy        float  — any of top 4 picks was winner
        net_pnl              float  — total P&L in $ from flat win bets
        roi_pct              float  — ROI percentage
        total_staked         float  — total amount staked
        n_races              int    — number of matched races
        detail_df            pd.DataFrame — per-race breakdown
    """
    if picks_df.empty or results_df.empty:
        return _empty_metrics()

    # Normalise for matching
    picks = picks_df.copy()
    results = results_df.copy()
    picks["_venue_norm"] = picks["venue"].apply(_normalise_name)
    results["_venue_norm"] = results["venue"].apply(_normalise_name)

    # Top pick per race (rank 1 only)
    top_picks = picks[picks["predicted_rank"] == 1].copy()

    detail_rows = []

    for _, top in top_picks.iterrows():
        v_norm = top["_venue_norm"]
        rn = top["race_number"]

        # Match result
        match = results[
            (results["_venue_norm"] == v_norm) & (results["race_number"] == rn)
        ]
        if match.empty:
            continue

        result_row = match.iloc[0]
        winner = str(result_row["winner"]).strip().lower()
        predicted_name = str(top["dog_name"]).strip().lower()

        # Get all 4 predictions for this race
        race_preds = picks[
            (picks["_venue_norm"] == v_norm) & (picks["race_number"] == rn)
        ]["dog_name"].str.strip().str.lower().tolist()

        # Finishing order (if available)
        finishing_order_raw = str(result_row.get("finishing_order", ""))
        finishing_order = [x.strip().lower() for x in finishing_order_raw.split("|") if x.strip()]

        is_top_pick_win = (predicted_name == winner)
        is_top_pick_place = (
            predicted_name in finishing_order[:3] if finishing_order else is_top_pick_win
        )
        is_top4_correct = (winner in race_preds)

        # P&L: flat win bet on top pick
        implied_odds = top.get("implied_odds", 2.0)
        try:
            odds = float(implied_odds) if pd.notna(implied_odds) else 2.0
        except (ValueError, TypeError):
            odds = 2.0
        if is_top_pick_win:
            pnl = round(bet_amount * (odds - 1), 2)
        else:
            pnl = -bet_amount

        detail_rows.append({
            "venue": top["venue"],
            "race_number": rn,
            "predicted_dog": top["dog_name"],
            "actual_winner": result_row["winner"],
            "win_prob": top.get("win_prob", None),
            "implied_odds": implied_odds,
            "top_pick_win": is_top_pick_win,
            "top_pick_place": is_top_pick_place,
            "top4_correct": is_top4_correct,
            "stake": bet_amount,
            "pnl": pnl,
        })

    if not detail_rows:
        return _empty_metrics()

    detail_df = pd.DataFrame(detail_rows)
    n_races = len(detail_df)
    n_win = int(detail_df["top_pick_win"].sum())
    n_place = int(detail_df["top_pick_place"].sum())
    n_top4 = int(detail_df["top4_correct"].sum())
    net_pnl = round(float(detail_df["pnl"].sum()), 2)
    total_staked = round(bet_amount * n_races, 2)
    roi_pct = round((net_pnl / total_staked) * 100, 1) if total_staked > 0 else 0.0

    return {
        "top_pick_hit_rate": round(n_win / n_races, 4) if n_races else 0.0,
        "top_pick_place_rate": round(n_place / n_races, 4) if n_races else 0.0,
        "top4_accuracy": round(n_top4 / n_races, 4) if n_races else 0.0,
        "net_pnl": net_pnl,
        "roi_pct": roi_pct,
        "total_staked": total_staked,
        "n_races": n_races,
        "detail_df": detail_df,
    }


def _empty_metrics() -> dict[str, Any]:
    """Return a zeroed-out metrics dict when no data is available."""
    return {
        "top_pick_hit_rate": 0.0,
        "top_pick_place_rate": 0.0,
        "top4_accuracy": 0.0,
        "net_pnl": 0.0,
        "roi_pct": 0.0,
        "total_staked": 0.0,
        "n_races": 0,
        "detail_df": pd.DataFrame(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Persist results
# ──────────────────────────────────────────────────────────────────────────────

def append_results_log(metrics: dict[str, Any], date_str: str) -> None:
    """
    Append per-race result rows to outputs/results_log.csv.

    Parameters
    ----------
    metrics : dict
        Output of compare_predictions().
    date_str : str
        Date string in YYYY-MM-DD format.
    """
    detail_df: pd.DataFrame = metrics.get("detail_df", pd.DataFrame())
    if detail_df.empty:
        print("[track_results] No detail rows to log.")
        return

    detail_df = detail_df.copy()
    detail_df.insert(0, "date", date_str)

    outputs_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    log_path = os.path.join(outputs_dir, "results_log.csv")

    if os.path.exists(log_path):
        # Remove any existing rows for this date before appending
        existing = pd.read_csv(log_path)
        existing = existing[existing["date"] != date_str]
        combined = pd.concat([existing, detail_df], ignore_index=True)
    else:
        combined = detail_df

    combined.to_csv(log_path, index=False)
    print(f"[track_results] Appended {len(detail_df)} rows to {log_path}")


def save_daily_summary(metrics: dict[str, Any], date_str: str) -> None:
    """
    Upsert a daily summary row into outputs/daily_summary.csv.

    Parameters
    ----------
    metrics : dict
        Output of compare_predictions().
    date_str : str
        Date string in YYYY-MM-DD format.
    """
    row = {
        "date": date_str,
        "n_races": metrics.get("n_races", 0),
        "top_pick_hit_rate": metrics.get("top_pick_hit_rate", 0.0),
        "top_pick_place_rate": metrics.get("top_pick_place_rate", 0.0),
        "top4_accuracy": metrics.get("top4_accuracy", 0.0),
        "net_pnl": metrics.get("net_pnl", 0.0),
        "total_staked": metrics.get("total_staked", 0.0),
        "roi_pct": metrics.get("roi_pct", 0.0),
    }

    outputs_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    summary_path = os.path.join(outputs_dir, "daily_summary.csv")

    new_row_df = pd.DataFrame([row])

    if os.path.exists(summary_path):
        existing = pd.read_csv(summary_path)
        existing = existing[existing["date"] != date_str]
        combined = pd.concat([existing, new_row_df], ignore_index=True)
    else:
        combined = new_row_df

    combined.to_csv(summary_path, index=False)
    print(f"[track_results] Daily summary updated at {summary_path}")


def print_pnl_summary(metrics: dict[str, Any]) -> None:
    """Print a formatted P&L summary to stdout."""
    n = metrics.get("n_races", 0)
    if n == 0:
        print("[track_results] No matched races — cannot compute P&L.")
        return

    hit = metrics.get("top_pick_hit_rate", 0.0)
    place = metrics.get("top_pick_place_rate", 0.0)
    top4 = metrics.get("top4_accuracy", 0.0)
    pnl = metrics.get("net_pnl", 0.0)
    roi = metrics.get("roi_pct", 0.0)
    staked = metrics.get("total_staked", 0.0)
    currency = "AUD"

    print(f"\n{'='*60}")
    print(f"  P&L SUMMARY")
    print(f"{'='*60}")
    print(f"  Races tracked      : {n}")
    print(f"  Top pick hit rate  : {hit:.1%}")
    print(f"  Top pick place rate: {place:.1%}")
    print(f"  Top-4 accuracy     : {top4:.1%}")
    print(f"  Total staked       : {currency} ${staked:.2f}")
    print(f"  Net P&L            : {currency} ${pnl:+.2f}")
    print(f"  ROI                : {roi:+.1f}%")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch race results and compute P&L against predictions."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date to track (YYYY-MM-DD). Defaults to today AEST.",
    )
    parser.add_argument(
        "--bet-amount",
        type=float,
        default=None,
        help="Flat stake per race in AUD (overrides config). Default: 10.0",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: fetch results for a date and compute P&L vs picks."""
    args = _parse_args()

    # Resolve date
    if args.date:
        date_str = args.date
    else:
        date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    # Load config for bet amount
    bet_amount = args.bet_amount
    if bet_amount is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from src.config_loader import load_config
            cfg = load_config()
            bet_amount = float(cfg.get("tracking", {}).get("bet_amount", 10.0))
        except Exception:
            bet_amount = 10.0

    # Load picks
    picks_path = os.path.join("outputs", f"picks_{date_str}.csv")
    if not os.path.exists(picks_path):
        print(f"[track_results] ERROR: Picks file not found: {picks_path}")
        print("  Run 'python run_pipeline.py --date {date_str}' first.")
        sys.exit(1)

    print(f"[track_results] Loading picks from {picks_path}")
    picks_df = pd.read_csv(picks_path)

    if "venue" not in picks_df.columns or "race_number" not in picks_df.columns:
        print("[track_results] ERROR: picks CSV missing required columns (venue, race_number).")
        sys.exit(1)

    venues = picks_df["venue"].dropna().unique().tolist()
    print(f"[track_results] Venues in picks: {venues}")

    # Fetch results
    results_df = fetch_all_results(date_str, venues)

    if results_df.empty:
        print(f"[track_results] No results available for {date_str}. "
              "Races may not be complete yet.")
        sys.exit(0)

    # Compare
    metrics = compare_predictions(picks_df, results_df, bet_amount=bet_amount)
    print_pnl_summary(metrics)

    # Save
    append_results_log(metrics, date_str)
    save_daily_summary(metrics, date_str)


if __name__ == "__main__":
    main()
