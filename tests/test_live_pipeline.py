import pandas as pd

from src.data import tab_api
from src.tab_pipeline_service import PipelineOptions, _apply_race_filters, _enforce_deploy_guard, run_pipeline


def test_fetch_all_races_with_diagnostics_collects_skips(monkeypatch):
    monkeypatch.setattr(
        tab_api,
        "fetch_meetings",
        lambda _date: [{"venueMnemonic": "AP", "meetingName": "Angle Park", "races": [1, 2]}],
    )

    def fake_fetch_race(_date, _venue, race_num):
        if race_num == 1:
            return None
        return {
            "race_number": 2,
            "distance": 500,
            "grade": "Grade 5",
            "runners": [],
        }

    monkeypatch.setattr(tab_api, "fetch_race", fake_fetch_race)

    df, skipped = tab_api.fetch_all_races_with_diagnostics("2026-04-25")

    assert df.empty
    assert len(skipped) == 2
    assert {s["reason"] for s in skipped} == {"race_fetch_failed", "no_runners"}


def test_race_filters_apply_all_guards():
    raw_df = pd.DataFrame([
        {"venue": "A", "race_number": 1, "dog_name": "", "grade": "Grade 5"},
        {"venue": "A", "race_number": 1, "dog_name": "DOG 2", "grade": "Grade 5"},
        {"venue": "A", "race_number": 1, "dog_name": "DOG 3", "grade": "Grade 5"},
        {"venue": "A", "race_number": 1, "dog_name": "DOG 4", "grade": "Grade 5"},
        {"venue": "A", "race_number": 1, "dog_name": "DOG 5", "grade": "Grade 5"},
        {"venue": "A", "race_number": 2, "dog_name": "DOG 1", "grade": "Maiden"},
        {"venue": "A", "race_number": 2, "dog_name": "DOG 2", "grade": "Maiden"},
        {"venue": "A", "race_number": 2, "dog_name": "DOG 3", "grade": "Maiden"},
        {"venue": "A", "race_number": 2, "dog_name": "DOG 4", "grade": "Maiden"},
        {"venue": "A", "race_number": 2, "dog_name": "DOG 5", "grade": "Maiden"},
    ])
    meta = {"source": "csv", "skipped_races": []}
    filtered = _apply_race_filters(raw_df, meta)
    assert filtered.empty
    reasons = {x["reason"] for x in meta["skipped_races"]}
    assert "vacant_runner_filtered" in reasons
    assert "insufficient_valid_runners" in reasons
    assert "low_information_maiden" in reasons


def test_deploy_guard_blocks_box1_and_maiden():
    picks = [{"venue": "A", "race_number": 1, "dog_name": "DOG 1", "box": 1}]
    preds = pd.DataFrame([
        {"_venue": "A", "_race_number": 1, "_dog_name": "DOG 1", "_grade": "Maiden"}
    ])
    try:
        _enforce_deploy_guard(picks, preds)
        assert False
    except RuntimeError as exc:
        assert "Box 1" in str(exc)


def test_run_pipeline_writes_latest_csv(monkeypatch, tmp_path):
    raw_df = pd.DataFrame([
        {"venue": "Angle Park", "race_number": 1, "dog_name": f"DOG {i}", "dog_number": i, "track": "AP", "grade": "Grade 5"}
        for i in range(1, 6)
    ])
    predictions_df = pd.DataFrame(
        [
            {
                "_venue": "Angle Park",
                "_race_number": 1,
                "_dog_name": "DOG A",
                "_dog_number": 2,
                "_grade": "Grade 5",
                "FinalScore": 1.5,
                "model_prob": 0.4,
                "_odds": 3.0,
            }
        ]
    )

    monkeypatch.setattr("src.tab_pipeline_service._HERE", str(tmp_path))
    monkeypatch.setattr("src.tab_pipeline_service.load_config", lambda: {"tracking": {"bet_amount": 10}})
    monkeypatch.setattr(
        "src.tab_pipeline_service._load_raw_data",
        lambda options, _config: (raw_df, options.date or "2026-04-25", {"source": options.source, "skipped_races": []}),
    )
    monkeypatch.setattr("src.tab_pipeline_service.engineer_features", lambda _df: predictions_df.copy())
    monkeypatch.setattr("src.tab_pipeline_service.predict_with_models", lambda df: df)
    monkeypatch.setattr(
        "src.tab_pipeline_service.select_bets",
        lambda *_args, **_kwargs: [
            {
                "venue": "Angle Park",
                "race_number": 1,
                "dog_name": "DOG A",
                "box": 2,
                "model_prob": 0.4,
                "odds": 3.0,
                "overlay_pct": 20.0,
                "confidence": "MEDIUM",
                "bet_amount": 10,
            }
        ],
    )

    result = run_pipeline(PipelineOptions(source="csv", date="2026-04-25", dry_run=False))

    assert "latest_csv" in result["outputs"]
    assert (tmp_path / "latest_picks.json").exists()
    assert (tmp_path / "latest_picks.csv").exists()
