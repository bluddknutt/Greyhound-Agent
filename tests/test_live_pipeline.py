import pandas as pd

from src.data import tab_api
from src.tab_pipeline_service import PipelineOptions, run_pipeline


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


def test_run_pipeline_writes_latest_csv(monkeypatch, tmp_path):
    raw_df = pd.DataFrame(
        [
            {
                "venue": "Angle Park",
                "race_number": 1,
                "dog_name": "DOG A",
                "dog_number": 1,
                "track": "AP",
            }
        ]
    )
    predictions_df = pd.DataFrame(
        [
            {
                "_venue": "Angle Park",
                "_race_number": 1,
                "_dog_name": "DOG A",
                "_dog_number": 1,
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
                "box": 1,
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
