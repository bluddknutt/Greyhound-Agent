"""Mobile-first Flask web app for running the TAB prediction pipeline."""

from __future__ import annotations

import os
from flask import Flask, jsonify, render_template, request

from src.results_store import (
    fetch_latest_run,
    fetch_races_for_date,
    fetch_run_history,
    performance_summary,
    record_run,
)
from src.tab_pipeline_service import PipelineOptions, run_pipeline

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/run", methods=["POST"])
def run_route():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source", "csv")
    date = payload.get("date")
    venue = payload.get("venue")
    csv_dir = payload.get("csv_dir", "./race_data/")
    dry_run = bool(payload.get("dry_run", False))

    try:
        result = run_pipeline(
            PipelineOptions(
                source=source,
                date=date,
                venue=venue,
                csv_dir=csv_dir,
                dry_run=dry_run,
            )
        )
        run_id = record_run(result, status="success")
        return jsonify({"ok": True, "run_id": run_id, "result": result})
    except Exception as exc:
        record_run(
            {
                "source": source,
                "run_date": date or "",
                "venue_filter": venue,
                "dry_run": dry_run,
                "summary": {},
            },
            status="failed",
            error=str(exc),
        )
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/results/latest")
def latest_results():
    latest = fetch_latest_run()
    if not latest:
        return jsonify({"ok": True, "result": None})
    return jsonify({"ok": True, "result": latest, "performance": performance_summary()})


@app.route("/results/history")
def result_history():
    limit = int(request.args.get("limit", 25))
    return jsonify({"ok": True, "history": fetch_run_history(limit=limit), "performance": performance_summary()})


@app.route("/races/<run_date>")
def races_by_date(run_date: str):
    races = fetch_races_for_date(run_date)
    return jsonify({"ok": True, "date": run_date, "races": races})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
