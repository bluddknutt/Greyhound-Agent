import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_offline_smoke_creates_non_empty_outputs_with_expected_schema():
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "run_live_pipeline.py", "--offline-smoke"]
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr or proc.stdout

    latest_json = repo_root / "latest_picks.json"
    latest_csv = repo_root / "latest_picks.csv"

    assert latest_json.exists()
    assert latest_json.stat().st_size > 0

    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert {"generated_at", "source", "date", "picks", "summary"}.issubset(payload.keys())

    picks = payload["picks"]
    assert isinstance(picks, list)
    assert picks

    required_pick_fields = {
        "venue", "race_number", "dog_name", "box", "model_prob",
        "odds", "overlay_pct", "confidence", "bet_amount", "danger",
    }
    for pick in picks:
        assert required_pick_fields.issubset(pick.keys())
        name = pick["dog_name"].lower()
        assert "scratch" not in name
        assert "vacant" not in name

    assert latest_csv.exists()
    assert latest_csv.stat().st_size > 0

    csv_df = pd.read_csv(latest_csv)
    assert not csv_df.empty
    assert list(csv_df.columns) == [
        "venue", "race", "box", "dog_name", "model_prob", "odds", "overlay_pct", "confidence", "bet_amount"
    ]
