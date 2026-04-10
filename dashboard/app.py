"""
Flask dashboard for the Greyhound prediction pipeline.

Serves a single-page dark-themed dashboard showing today's predictions,
with auto-refresh every 5 minutes and optional ngrok tunnel.

Usage:
    python dashboard/app.py           # http://localhost:5000
    python dashboard/app.py --ngrok   # with public ngrok URL
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
from flask import Flask, jsonify, render_template

# Ensure project root is importable
_DASH_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DASH_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.config_loader import load_config

AEST = timezone(timedelta(hours=10))

app = Flask(__name__, template_folder="templates", static_folder="static")
_config = load_config()


# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_today_aest() -> str:
    return datetime.now(AEST).strftime("%Y-%m-%d")


def load_picks(date_str: str) -> pd.DataFrame:
    """
    Load picks_{date}.csv from the outputs directory.

    Returns empty DataFrame if file not found.
    """
    path = os.path.join(_ROOT, "outputs", f"picks_{date_str}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        print(f"[dashboard] WARNING: Could not load {path}: {exc}")
        return pd.DataFrame()


def load_daily_summary(date_str: str) -> dict:
    """Load the daily P&L summary row for the given date (if available)."""
    path = os.path.join(_ROOT, "outputs", "daily_summary.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        row = df[df["date"] == date_str]
        if row.empty:
            return {}
        return row.iloc[0].to_dict()
    except Exception:
        return {}


def build_summary(df: pd.DataFrame) -> dict:
    """Compute summary statistics from a picks DataFrame."""
    if df.empty:
        return {
            "n_venues": 0,
            "n_races": 0,
            "strong_picks": 0,
            "avg_top_win_prob": 0.0,
            "last_updated": "—",
        }

    threshold = float(_config.get("scorer", {}).get("min_win_prob_threshold", 0.15))
    strong_threshold = 0.25

    top_picks = df[df["predicted_rank"] == 1] if "predicted_rank" in df.columns else df

    n_venues = int(df["venue"].nunique()) if "venue" in df.columns else 0
    n_races = int(df.groupby(["venue", "race_number"]).ngroups) if "venue" in df.columns else 0
    strong_picks = int(
        (top_picks["win_prob"] > strong_threshold).sum()
    ) if "win_prob" in top_picks.columns else 0
    avg_win_prob = float(top_picks["win_prob"].mean()) if "win_prob" in top_picks.columns else 0.0

    # File modification time as last_updated
    outputs_path = os.path.join(_ROOT, "outputs")
    date_str = get_today_aest()
    picks_path = os.path.join(outputs_path, f"picks_{date_str}.csv")
    if os.path.exists(picks_path):
        mtime = os.path.getmtime(picks_path)
        last_updated = datetime.fromtimestamp(mtime, tz=AEST).strftime("%H:%M AEST")
    else:
        last_updated = "—"

    return {
        "n_venues": n_venues,
        "n_races": n_races,
        "strong_picks": strong_picks,
        "avg_top_win_prob": round(avg_win_prob * 100, 1),
        "last_updated": last_updated,
    }


def picks_to_json(df: pd.DataFrame) -> list:
    """
    Convert picks DataFrame to a nested JSON structure:
    [{ venue, state, races: [{ race_number, race_time, distance, grade,
                               race_name, runners: [...] }] }]
    """
    if df.empty:
        return []

    result = []
    for venue in sorted(df["venue"].unique()):
        venue_df = df[df["venue"] == venue]
        state = ""
        if "state" in venue_df.columns:
            s = venue_df["state"].dropna()
            state = str(s.iloc[0]) if not s.empty else ""

        races = []
        for race_num in sorted(venue_df["race_number"].unique()):
            race_df = venue_df[venue_df["race_number"] == race_num].sort_values(
                "predicted_rank"
            )

            # Race metadata from first row
            first = race_df.iloc[0]
            race_time = str(first.get("race_time", ""))
            try:
                dt = datetime.fromisoformat(race_time)
                race_time_fmt = dt.strftime("%I:%M %p")
            except (ValueError, TypeError):
                race_time_fmt = race_time

            runners = []
            for _, row in race_df.iterrows():
                win_prob = row.get("win_prob", None)
                implied_odds = row.get("implied_odds", None)
                composite = row.get("composite", None)

                runners.append({
                    "rank": int(row.get("predicted_rank", 1)),
                    "box": str(row.get("box", "")),
                    "dog_name": str(row.get("dog_name", "")),
                    "trainer": str(row.get("trainer", "")),
                    "composite": round(float(composite), 3) if composite is not None and pd.notna(composite) else None,
                    "win_prob": round(float(win_prob) * 100, 1) if win_prob is not None and pd.notna(win_prob) else None,
                    "implied_odds": round(float(implied_odds), 1) if implied_odds is not None and pd.notna(implied_odds) else None,
                    "speed_norm": _safe_round(row.get("speed_score_norm")),
                    "form_norm": _safe_round(row.get("form_score_norm")),
                    "box_norm": _safe_round(row.get("box_bias_norm")),
                    "class_norm": _safe_round(row.get("class_rating_norm")),
                    "pace_norm": _safe_round(row.get("early_speed_norm")),
                    "con_norm": _safe_round(row.get("consistency_norm")),
                    "fit_norm": _safe_round(row.get("track_fitness_norm")),
                })

            races.append({
                "race_number": int(race_num),
                "race_time": race_time_fmt,
                "distance": str(first.get("distance", "")),
                "grade": str(first.get("grade", "")),
                "race_name": str(first.get("race_name", "")),
                "runners": runners,
            })

        result.append({"venue": venue, "state": state, "races": races})

    return result


def _safe_round(val, digits: int = 2):
    """Return rounded float or None if not a valid number."""
    try:
        if val is None or pd.isna(val):
            return None
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Render the main dashboard page."""
    date_str = get_today_aest()
    refresh = int(_config.get("dashboard", {}).get("refresh_interval", 300))
    return render_template("index.html", date=date_str, refresh_interval=refresh)


@app.route("/api/summary")
def api_summary():
    """Return summary statistics as JSON."""
    date_str = get_today_aest()
    df = load_picks(date_str)
    summary = build_summary(df)
    summary["date"] = date_str
    pnl = load_daily_summary(date_str)
    if pnl:
        summary["pnl"] = {
            "hit_rate": round(float(pnl.get("top_pick_hit_rate", 0)) * 100, 1),
            "place_rate": round(float(pnl.get("top_pick_place_rate", 0)) * 100, 1),
            "top4_accuracy": round(float(pnl.get("top4_accuracy", 0)) * 100, 1),
            "net_pnl": float(pnl.get("net_pnl", 0)),
            "roi_pct": float(pnl.get("roi_pct", 0)),
            "n_races": int(pnl.get("n_races", 0)),
        }
    return jsonify(summary)


@app.route("/api/picks")
def api_picks():
    """Return today's picks as nested JSON."""
    date_str = get_today_aest()
    df = load_picks(date_str)
    return jsonify(picks_to_json(df))


@app.route("/api/results")
def api_results():
    """Return daily P&L summary as JSON (if available)."""
    date_str = get_today_aest()
    return jsonify(load_daily_summary(date_str))


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    use_ngrok = "--ngrok" in sys.argv
    port = int(_config.get("dashboard", {}).get("port", 5000))

    if use_ngrok:
        try:
            from pyngrok import ngrok
            tunnel = ngrok.connect(port)
            public_url = tunnel.public_url
            print(f"\n[dashboard] ngrok public URL: {public_url}\n")
            outputs_dir = os.path.join(_ROOT, "outputs")
            os.makedirs(outputs_dir, exist_ok=True)
            url_file = os.path.join(outputs_dir, "dashboard_url.txt")
            with open(url_file, "w") as fh:
                fh.write(public_url)
            print(f"[dashboard] URL saved to {url_file}")
        except ImportError:
            print("[dashboard] WARNING: pyngrok not installed. Run: pip install pyngrok")
        except Exception as exc:
            print(f"[dashboard] WARNING: ngrok failed: {exc}")

    print(f"[dashboard] Starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
