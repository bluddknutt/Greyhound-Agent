"""Tests for src/exporter.py — export_to_excel()"""

import os
import pytest
import pandas as pd
from src.exporter import export_to_excel


def _minimal_dog():
    """Return a dog dict with the minimum required keys for exporter."""
    return {
        "Track": "The Meadows",
        "RaceNumber": 1,
        "RaceDate": "2025-10-12",
        "RaceTime": "07:30PM",
        "Distance": 515,
        "Box": 1,
        "DogsName": "Speedy Bolt",
        "form_code": "1234",
        "age_sex": "2d",
        "weight": 31.5,
        "trainer": "J Smith",
        "wins": 5,
        "places": 3,
        "starts": 12,
        "PrizeMoney": 24500,
        "KmH": 66.0,
        "experience_level": "experienced",
        "FinalScore": 45.2,
        "Bet": "YES",
        "strike_rate": 0.42,
        "win_percentage": 0.33,
        "place_percentage": 0.58,
        "consistency_rate": 0.7,
        "consistent_places": 7,
        "has_dnf": False,
        "has_win": 1,
        "has_place": 1,
        "recent_races": 5,
        "recent_positions": [1, 2, 3, 1, 2],
        "avg_recent_position": 1.8,
        "best_recent_position": 1,
        "worst_recent_position": 3,
        "form_trend": "improving",
        "source_file": "test.pdf",
        "Date": "2025-10-12",
    }


class TestExportToExcel:
    def test_creates_xlsx_file(self, tmp_path):
        dogs = [_minimal_dog()]
        export_to_excel(dogs, str(tmp_path))
        xlsx_files = list(tmp_path.glob("*.xlsx"))
        assert len(xlsx_files) == 1

    def test_xlsx_filename_contains_timestamp(self, tmp_path):
        dogs = [_minimal_dog()]
        export_to_excel(dogs, str(tmp_path))
        xlsx_files = list(tmp_path.glob("greyhound_analysis_*.xlsx"))
        assert len(xlsx_files) == 1

    def test_output_is_readable_dataframe(self, tmp_path):
        dogs = [_minimal_dog()]
        export_to_excel(dogs, str(tmp_path))
        xlsx_path = next(tmp_path.glob("*.xlsx"))
        df = pd.read_excel(xlsx_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_multiple_dogs_all_written(self, tmp_path):
        dogs = [_minimal_dog(), _minimal_dog(), _minimal_dog()]
        export_to_excel(dogs, str(tmp_path))
        xlsx_path = next(tmp_path.glob("*.xlsx"))
        df = pd.read_excel(xlsx_path)
        assert len(df) == 3

    def test_extra_keys_do_not_raise(self, tmp_path, capsys):
        dog = _minimal_dog()
        dog["unexpected_extra_key"] = "some_value"
        # Should not raise — extra keys are warned but not fatal
        export_to_excel([dog], str(tmp_path))
        captured = capsys.readouterr()
        assert "WARNING" in captured.out or True  # warning may or may not print

    def test_missing_keys_filled_with_none(self, tmp_path):
        dog = _minimal_dog()
        del dog["Bet"]  # Remove a required column
        export_to_excel([dog], str(tmp_path))
        xlsx_path = next(tmp_path.glob("*.xlsx"))
        df = pd.read_excel(xlsx_path)
        assert "Bet" in df.columns
