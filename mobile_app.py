"""Installable mobile-first Flask app for Greyhound-Agent."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from src.results_store import (
    fetch_latest_run,
    fetch_races_for_date,
    fetch_run_history,
    get_connection,
    init_db,
    performance_summary,
    record_run,
)
from src.tab_pipeline_service import PipelineOptions, run_pipeline

AEST = timezone(timedelta(hours=10))

app = Flask(
    __name__,
    template_folder="mobile_web/templates",
    static_folder="mobile_web/static",
)


def _today_aest() -> str:
    return datetime.now(AEST).strftime("%Y-%m-%d")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _run_defaults() -> dict[str, Any]:
    return {
        "source": "csv",
        "date": _today_aest(),
        "venue": "",
        "csv_dir": "./race_data/",
        "dry_run": False,
    }


def fetch_run_by_id(run_id: int) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload["run_id"] = row["id"]
    payload["status"] = row["status"]
    payload["error"] = row["error"]
    payload["created_at"] = row["created_at"]
    return payload


def _normalise_run_payload(payload: dict[str, Any]) -> PipelineOptions:
    source = _clean_text(payload.get("source")) or "csv"
    date = _clean_text(payload.get("date"))
    venue = _clean_text(payload.get("venue"))
    csv_dir = _clean_text(payload.get("csv_dir")) or "./race_data/"
    dry_run = bool(payload.get("dry_run", False))
    return PipelineOptions(
        source=source,
        date=date,
        venue=venue,
        csv_dir=csv_dir,
        dry_run=dry_run,
    )


@app.route("/")
def index() -> str:
    return render_template("index.html", defaults=_run_defaults())


@app.route("/health")
def health() -> Response:
    return jsonify({"status": "ok", "app": "greyhound-mobile"})


@app.route("/manifest.webmanifest")
def manifest() -> Response:
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker() -> Response:
    response = send_from_directory(app.static_folder, "service-worker.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/api/meta")
def meta() -> Response:
    return jsonify(
        {
            "ok": True,
            "defaults": _run_defaults(),
            "sources": [
                {"value": "csv", "label": "CSV"},
                {"value": "tab", "label": "TAB API"},
                {"value": "scrape", "label": "Scrape thedogs.com.au"},
            ],
            "notes": {
                "tab": "TAB API can fail outside Australia due to IP restrictions.",
                "scrape": "Scrape source depends on thedogs.com.au availability.",
            },
        }
    )


@app.route("/api/run", methods=["POST"])
def run_route() -> Response:
    payload = request.get_json(silent=True) or {}
    options = _normalise_run_payload(payload)

    try:
        result = run_pipeline(options)
        run_id = record_run(result, status="success")
    except Exception as exc:  # pragma: no cover - exercised in integration environments
        record_run(
            {
                "source": options.source,
                "run_date": options.date or "",
                "venue_filter": options.venue,
                "dry_run": options.dry_run,
                "summary": {},
            },
            status="failed",
            error=str(exc),
        )
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "run_id": run_id,
            "result": result,
            "performance": performance_summary(),
        }
    )


@app.route("/api/results/latest")
def latest_results() -> Response:
    latest = fetch_latest_run()
    return jsonify(
        {
            "ok": True,
            "result": latest,
            "performance": performance_summary(),
        }
    )


@app.route("/api/results/history")
def result_history() -> Response:
    raw_limit = request.args.get("limit", "25")
    try:
        limit = max(1, min(int(raw_limit), 100))
    except ValueError:
        limit = 25
    return jsonify(
        {
            "ok": True,
            "history": fetch_run_history(limit=limit),
            "performance": performance_summary(),
        }
    )


@app.route("/api/results/<int:run_id>")
def run_detail(run_id: int) -> Response:
    result = fetch_run_by_id(run_id)
    if not result:
        return jsonify({"ok": False, "error": "Run not found"}), 404
    return jsonify({"ok": True, "result": result})


@app.route("/api/races/<run_date>")
def races_by_date(run_date: str) -> Response:
    races = fetch_races_for_date(run_date)
    return jsonify({"ok": True, "date": run_date, "races": races})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
