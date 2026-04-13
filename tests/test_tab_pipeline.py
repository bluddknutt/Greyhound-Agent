"""
Tests for the TAB pipeline components:
  - CSV ingestion (csv_ingest.py)
  - Feature engineering (tab_feature_engineer.py)
  - Model prediction (run_tab_pipeline.py model loading)
  - Bet selection (bet_selector.py)
  - Print Hub scraper (thedogs_scraper.py)
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# Ensure project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.data.csv_ingest import (
    load_race_csv,
    load_meeting_csvs,
    validate_csv_headers,
    _clean_grade,
    _parse_dog_name,
    _parse_filename,
)
from src.tab_feature_engineer import (
    MODEL_FEATURES,
    engineer_features,
    _grade_to_num,
    _parse_pir,
    _parse_last_starts,
    _generic_box_advantage,
)
from src.bet_selector import (
    select_bets,
    format_picks_json,
)


# ── Sample CSV content ───────────────────────────────────────────────────────

SAMPLE_CSV = """\
Dog Name,Sex,PLC,BOX,WGT,DIST,DATE,TRACK,G,TIME,WIN,BON,1 SEC,MGN,W/2G,PIR,SP
1. FAST RUNNER,D,1,3,31.4,300,2026-04-03,HEA,Tier 3 - Maiden,17.589,17.381,16.935,4.17,0.0,FAST RUNNER,311,3.5
"",D,3,5,31.4,300,2026-03-27,HEA,Maiden,17.356,16.805,16.754,4.20,3.0,SOPHIE BANJO,533,6.5
"",D,2,3,31.2,300,2026-03-20,HEA,Maiden,17.500,17.100,16.900,4.30,2.5,TOP DOG,322,5.0
2. SLOW STARTER,B,5,7,28.1,300,2026-04-03,HEA,Tier 3 - Maiden,18.200,17.381,16.935,4.50,8.0,FAST RUNNER,876,16.0
"",B,4,2,28.0,300,2026-03-27,HEA,Maiden,18.100,16.805,16.754,4.55,6.0,SOPHIE BANJO,765,12.0
3. MID PACK,D,2,1,30.0,300,2026-04-03,HEA,Tier 3 - Maiden,17.700,17.381,16.935,4.25,1.5,FAST RUNNER,432,5.0
"""


def _write_sample_csv(tmpdir, filename="Race_1_-_HEA_-_08_April_2026.csv"):
    """Write sample CSV to a temp directory and return the filepath."""
    filepath = os.path.join(tmpdir, filename)
    with open(filepath, "w") as f:
        f.write(SAMPLE_CSV)
    return filepath


# ═══════════════════════════════════════════════════════════════════════════
# TestCSVIngest
# ═══════════════════════════════════════════════════════════════════════════


class TestCSVIngest:
    """Tests for src/data/csv_ingest.py"""

    def test_parse_single_race_csv(self, tmp_path):
        """Load a sample CSV, verify dog count and column names."""
        filepath = _write_sample_csv(str(tmp_path))
        df = load_race_csv(filepath)

        assert not df.empty
        # 3 dogs: FAST RUNNER (3 lines), SLOW STARTER (2 lines), MID PACK (1 line)
        assert len(df) == 6  # total form lines
        assert df["dog_name"].nunique() == 3

        # Check required columns exist
        for col in ["dog_name", "dog_number", "box", "weight", "distance",
                     "time", "win_time", "grade", "race_number", "venue"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_parse_dog_name_strips_number(self):
        """'1. DOG NAME' → 'DOG NAME'"""
        name, num = _parse_dog_name("1. DOG NAME")
        assert name == "DOG NAME"
        assert num == 1

        name, num = _parse_dog_name("10. FAST RUNNER")
        assert name == "FAST RUNNER"
        assert num == 10

    def test_continuation_rows_grouped(self, tmp_path):
        """Continuation rows ('') attach to correct parent dog."""
        filepath = _write_sample_csv(str(tmp_path))
        df = load_race_csv(filepath)

        fast_runner = df[df["dog_name"] == "FAST RUNNER"]
        assert len(fast_runner) == 3  # header + 2 continuation rows
        assert fast_runner["run_sequence"].tolist() == [1, 2, 3]

    def test_missing_values_handled(self, tmp_path):
        """Empty fields become NaN."""
        csv_content = """\
Dog Name,Sex,PLC,BOX,WGT,DIST,DATE,TRACK,G,TIME,WIN,BON,1 SEC,MGN,W/2G,PIR,SP
1. TEST DOG,D,3,5,31.4,300,2026-04-03,HEA,Maiden,17.5,,,,,,3,
"""
        filepath = os.path.join(str(tmp_path), "Race_1_-_HEA_-_01_April_2026.csv")
        with open(filepath, "w") as f:
            f.write(csv_content)

        df = load_race_csv(filepath)
        assert len(df) == 1
        assert pd.isna(df.iloc[0]["win_time"])
        assert pd.isna(df.iloc[0]["bon"])
        assert pd.isna(df.iloc[0]["margin"])

    def test_grade_parsing(self):
        """Grade cleaning extracts clean grade names."""
        assert _clean_grade("Tier 3 - Maiden") == "Maiden"
        assert _clean_grade("Bottom Up - Grade 7") == "Grade 7"
        assert _clean_grade("Rank Limit - Restricted Win") == "Restricted Win"
        assert _clean_grade("Maiden") == "Maiden"
        assert _clean_grade("Grade 5") == "Grade 5"
        assert _clean_grade("Mixed 6/7 Heat") == "Mixed 6/7"

    def test_filename_parsing(self):
        """Extract race_number, venue, date from filename."""
        race_num, venue, date_str = _parse_filename(
            "Race_1_-_HEA_-_08_April_2026.csv"
        )
        assert race_num == 1
        assert venue == "HEA"
        assert date_str == "2026-04-08"

        race_num, venue, date_str = _parse_filename(
            "Race_12_-_Angle_Park_-_15_March_2026.csv"
        )
        assert race_num == 12
        assert venue == "Angle Park"

    def test_validate_csv_headers_valid(self, tmp_path):
        """Valid headers pass validation."""
        filepath = _write_sample_csv(str(tmp_path))
        valid, mismatched = validate_csv_headers(filepath)
        assert valid
        assert mismatched == []

    def test_load_meeting_csvs(self, tmp_path):
        """Load all CSVs from a directory."""
        _write_sample_csv(str(tmp_path), "Race_1_-_HEA_-_08_April_2026.csv")
        _write_sample_csv(str(tmp_path), "Race_2_-_HEA_-_08_April_2026.csv")

        df = load_meeting_csvs(str(tmp_path))
        assert not df.empty
        assert df["race_number"].nunique() == 2

    def test_load_meeting_csvs_venue_filter(self, tmp_path):
        """Venue filter excludes non-matching CSVs."""
        _write_sample_csv(str(tmp_path), "Race_1_-_HEA_-_08_April_2026.csv")
        _write_sample_csv(str(tmp_path), "Race_1_-_BAL_-_08_April_2026.csv")

        df = load_meeting_csvs(str(tmp_path), venue="HEA")
        assert not df.empty
        assert (df["venue"] == "HEA").all()


# ═══════════════════════════════════════════════════════════════════════════
# TestTabFeatureEngineer
# ═══════════════════════════════════════════════════════════════════════════


class TestTabFeatureEngineer:
    """Tests for src/tab_feature_engineer.py"""

    def _make_raw_df(self):
        """Create a minimal raw DataFrame for testing."""
        records = []
        for dog_num, dog_name in enumerate(["DOG_A", "DOG_B", "DOG_C"], 1):
            for seq in range(1, 4):  # 3 form lines each
                records.append({
                    "dog_name": dog_name,
                    "dog_number": dog_num,
                    "sex": "D",
                    "box": dog_num + 1,
                    "weight": 30.0 + dog_num * 0.5,
                    "distance": 300,
                    "date": pd.Timestamp("2026-04-01") - pd.Timedelta(days=seq * 7),
                    "track": "HEA",
                    "grade": "Maiden",
                    "race_number": 1,
                    "venue": "HEA",
                    "time": 17.5 + seq * 0.1 + dog_num * 0.2,
                    "win_time": 17.0 + seq * 0.05,
                    "bon": 16.8 + seq * 0.05,
                    "first_split": 4.2 + seq * 0.05,
                    "margin": dog_num * 1.5,
                    "w2g": "WINNER DOG",
                    "pir": "321",
                    "sp": 5.0 + dog_num,
                    "run_sequence": seq,
                })
        return pd.DataFrame(records)

    def test_produces_74_columns(self):
        """Feature engineering outputs exactly 74 model feature columns."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        feature_cols = [c for c in result.columns if not c.startswith("_")]
        assert len(feature_cols) == 74, (
            f"Expected 74 features, got {len(feature_cols)}. "
            f"Extra: {set(feature_cols) - set(MODEL_FEATURES)}, "
            f"Missing: {set(MODEL_FEATURES) - set(feature_cols)}"
        )

    def test_feature_names_match_model(self):
        """Feature names match MODEL_FEATURES exactly."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        feature_cols = [c for c in result.columns if not c.startswith("_")]
        assert set(feature_cols) == set(MODEL_FEATURES)

    def test_feature_order_matches_model(self):
        """Feature ORDER matches MODEL_FEATURES (critical for scaler)."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        feature_cols = [c for c in result.columns if not c.startswith("_")]
        assert feature_cols == MODEL_FEATURES, "Feature order mismatch"

    def test_no_nan_in_output(self):
        """No NaN values in feature columns after engineering."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        for col in MODEL_FEATURES:
            assert not result[col].isna().any(), f"NaN found in column: {col}"

    def test_speed_kmh_calculation(self):
        """Verify Speed_kmh = (Distance / BestTimeSec) * 3.6"""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        for _, row in result.iterrows():
            if row["BestTimeSec"] > 0:
                expected = (row["Distance"] / row["BestTimeSec"]) * 3.6
                assert abs(row["Speed_kmh"] - expected) < 0.01

    def test_consistency_index(self):
        """Verify ConsistencyIndex = CareerWins / CareerStarts."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        for _, row in result.iterrows():
            if row["CareerStarts"] > 0:
                expected = row["CareerWins"] / row["CareerStarts"]
                assert abs(row["ConsistencyIndex"] - expected) < 0.01

    def test_grade_to_num(self):
        """Grade mapping produces expected numeric values."""
        assert _grade_to_num("Maiden") == 1
        assert _grade_to_num("Grade 7") == 2
        assert _grade_to_num("FFA") == 7
        assert _grade_to_num("Open") == 8
        assert _grade_to_num(None) == 4  # default

    def test_pir_parsing(self):
        """PIR string parsing."""
        assert _parse_pir("321") == [3, 2, 1]
        assert _parse_pir("876") == [8, 7, 6]
        assert _parse_pir("") == []
        assert _parse_pir(None) == []

    def test_last_starts_parsing(self):
        """last5Starts string parsing."""
        assert _parse_last_starts("12341") == [1, 2, 3, 4, 1]
        assert _parse_last_starts("F8") == [8, 8]
        assert _parse_last_starts("") == []
        assert _parse_last_starts(None) == []

    def test_model_features_count(self):
        """MODEL_FEATURES has exactly 74 entries."""
        assert len(MODEL_FEATURES) == 74

    def test_one_row_per_dog(self):
        """Output has one row per unique dog (not per form line)."""
        raw_df = self._make_raw_df()
        result = engineer_features(raw_df)

        assert len(result) == 3  # 3 unique dogs

    def test_box_advantage(self):
        """Generic box advantage returns valid values."""
        assert 0 < _generic_box_advantage(1, 300) <= 1.0
        assert 0 < _generic_box_advantage(8, 500) <= 1.0
        assert _generic_box_advantage(1, 300) > _generic_box_advantage(6, 300)


# ═══════════════════════════════════════════════════════════════════════════
# TestModelPrediction
# ═══════════════════════════════════════════════════════════════════════════


class TestModelPrediction:
    """Tests for model loading in run_tab_pipeline.py"""

    def test_load_returns_none_for_unknown_venue(self):
        """Unknown venue returns None."""
        from run_tab_pipeline import _load_venue_models
        result = _load_venue_models("NONEXISTENT_VENUE")
        assert result is None

    def test_load_models_for_known_venue(self):
        """Known venue models load successfully (if pkl files exist)."""
        from run_tab_pipeline import _load_venue_models
        # Try loading Angle Park — should work if pkl files are in repo root
        result = _load_venue_models("Angle Park")
        if result is not None:
            gb, rf, scaler = result
            assert hasattr(gb, "predict_proba")
            assert hasattr(rf, "predict_proba")
            assert hasattr(scaler, "transform")

    def test_feature_alignment_check(self):
        """Model scaler features match MODEL_FEATURES."""
        from run_tab_pipeline import _load_venue_models
        result = _load_venue_models("Angle Park")
        if result is not None:
            _, _, scaler = result
            if hasattr(scaler, "feature_names_in_"):
                scaler_features = list(scaler.feature_names_in_)
                assert scaler_features == MODEL_FEATURES

    def test_fallback_for_missing_venue(self):
        """Venues without models get composite fallback probabilities."""
        from run_tab_pipeline import _predict_with_models

        # Create minimal features DataFrame
        records = []
        for i in range(3):
            feat = {f: 0.5 for f in MODEL_FEATURES}
            feat["FinalScore"] = 10.0 + i * 5
            feat["_dog_name"] = f"DOG_{i}"
            feat["_venue"] = "UNKNOWN_VENUE"
            feat["_race_number"] = 1
            feat["_dog_number"] = i + 1
            records.append(feat)

        df = pd.DataFrame(records)
        result = _predict_with_models(df)

        assert "model_prob" in result.columns
        assert result["model_prob"].notna().all()
        # Probabilities should sum to ~1 within the race
        assert abs(result["model_prob"].sum() - 1.0) < 0.01

    def test_resolve_model_prefix_handles_tab_name_variant(self):
        """TAB-style venue variants resolve to the correct model prefix."""
        from run_tab_pipeline import _resolve_model_prefix

        assert _resolve_model_prefix("Angle Park (SA)") == "Angle Park"
        assert _resolve_model_prefix("Some Different Name", venue_mnemonic="AP") == "Angle Park"


# ═══════════════════════════════════════════════════════════════════════════
# TestBetSelector
# ═══════════════════════════════════════════════════════════════════════════


class TestBetSelector:
    """Tests for src/bet_selector.py"""

    def _make_predictions(self, with_odds=True):
        """Create mock predictions DataFrame."""
        records = [
            {"_dog_name": "DOG_A", "_venue": "HEA", "_race_number": 1,
             "_dog_number": 1, "model_prob": 0.35, "_odds": 5.0 if with_odds else np.nan},
            {"_dog_name": "DOG_B", "_venue": "HEA", "_race_number": 1,
             "_dog_number": 2, "model_prob": 0.25, "_odds": 6.0 if with_odds else np.nan},
            {"_dog_name": "DOG_C", "_venue": "HEA", "_race_number": 1,
             "_dog_number": 3, "model_prob": 0.20, "_odds": 3.0 if with_odds else np.nan},
            {"_dog_name": "DOG_D", "_venue": "HEA", "_race_number": 2,
             "_dog_number": 4, "model_prob": 0.40, "_odds": 4.0 if with_odds else np.nan},
            {"_dog_name": "DOG_E", "_venue": "HEA", "_race_number": 2,
             "_dog_number": 5, "model_prob": 0.30, "_odds": 2.0 if with_odds else np.nan},
        ]
        return pd.DataFrame(records)

    def test_positive_overlay_selected(self):
        """Runners with positive overlay above threshold are selected."""
        df = self._make_predictions()
        picks = select_bets(df, {"tracking": {"min_overlay_pct": 10}})

        # DOG_A: 0.35 * 5.0 - 1 = 0.75 → 75% overlay (selected)
        # DOG_D: 0.40 * 4.0 - 1 = 0.60 → 60% overlay (selected)
        assert len(picks) >= 1
        dog_names = [p["dog_name"] for p in picks]
        assert "DOG_A" in dog_names

    def test_negative_overlay_filtered(self):
        """Runners with overlay below threshold are excluded."""
        # DOG_C: 0.20 * 3.0 - 1 = -0.40 → -40% (excluded)
        df = self._make_predictions()
        picks = select_bets(df, {"tracking": {"min_overlay_pct": 10}})

        dog_names = [p["dog_name"] for p in picks]
        assert "DOG_C" not in dog_names

    def test_one_bet_per_race(self):
        """At most one bet per race."""
        df = self._make_predictions()
        picks = select_bets(df)

        races = [(p["venue"], p["race_number"]) for p in picks]
        assert len(races) == len(set(races)), "Multiple bets in same race"

    def test_missing_odds_skipped_in_overlay_mode(self):
        """Runners with NaN odds are skipped when other runners have odds."""
        df = self._make_predictions()
        df.loc[0, "_odds"] = np.nan  # DOG_A has no odds

        picks = select_bets(df, {"tracking": {"min_overlay_pct": 10}})
        # DOG_A should not be selected (no odds)
        for p in picks:
            if p["race_number"] == 1:
                assert p["dog_name"] != "DOG_A"

    def test_output_schema(self):
        """Output dicts have all required keys."""
        df = self._make_predictions()
        picks = select_bets(df)

        required_keys = {"venue", "race_number", "dog_name", "box",
                         "model_prob", "odds", "overlay_pct", "confidence",
                         "bet_amount", "danger"}
        for p in picks:
            assert required_keys.issubset(p.keys()), (
                f"Missing keys: {required_keys - set(p.keys())}"
            )

    def test_csv_source_no_odds_mode(self):
        """When no odds available, ranks by model probability."""
        df = self._make_predictions(with_odds=False)
        picks = select_bets(df)

        # Should still produce picks (by probability)
        assert len(picks) > 0
        for p in picks:
            assert p["odds"] is None
            assert p["overlay_pct"] is None

    def test_format_picks_json_structure(self):
        """JSON output has required structure."""
        picks = [{"venue": "HEA", "race_number": 1, "dog_name": "DOG",
                  "box": 3, "model_prob": 0.35, "odds": 5.0,
                  "overlay_pct": 75.0, "confidence": "HIGH",
                  "bet_amount": 10, "danger": None}]
        result = format_picks_json(picks, "2026-04-08", source="csv")

        assert "generated_at" in result
        assert "source" in result
        assert result["source"] == "csv"
        assert "date" in result
        assert "picks" in result
        assert "summary" in result
        assert result["summary"]["total_picks"] == 1

    def test_generated_at_is_iso_format(self):
        """generated_at is valid ISO-8601."""
        result = format_picks_json([], "2026-04-08")
        # Should parse without error
        datetime.fromisoformat(result["generated_at"])


# ═══════════════════════════════════════════════════════════════════════════
# TestTheDogsScraper
# ═══════════════════════════════════════════════════════════════════════════


class TestTheDogsScraper:
    """Tests for src/scrapers/thedogs_scraper.py"""

    def test_slugify(self):
        """Venue name slugification."""
        from src.scrapers.thedogs_scraper import _slugify
        assert _slugify("Angle Park") == "angle_park"
        assert _slugify("Wentworth Park") == "wentworth_park"
        assert _slugify("HEA") == "hea"

    def test_skip_existing_files(self, tmp_path):
        """Existing files are not re-downloaded."""
        from src.scrapers.thedogs_scraper import download_file

        # Create an existing file
        existing = str(tmp_path / "existing.pdf")
        with open(existing, "w") as f:
            f.write("content")

        # download_file should return True without making a request
        result = download_file("https://example.com/fake.pdf", existing)
        assert result is True

    def test_directory_structure_created(self, tmp_path):
        """Download creates directory structure."""
        from src.scrapers.thedogs_scraper import download_file

        dest = str(tmp_path / "2026-04-11" / "ballarat" / "test.pdf")
        # This will fail to download (fake URL) but should create dirs
        download_file("https://example.invalid/fake.pdf", dest)
        assert os.path.isdir(os.path.dirname(dest))

    def test_venue_filter(self):
        """Venue filter logic works correctly."""
        venues = [
            {"name": "Ballarat", "slug": "ballarat", "downloads": {}},
            {"name": "Bendigo", "slug": "bendigo", "downloads": {}},
        ]

        filter_lower = "ballarat"
        filtered = [
            v for v in venues
            if filter_lower in v["name"].lower() or filter_lower in v["slug"]
        ]
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Ballarat"
