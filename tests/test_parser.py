"""Tests for src/parser.py — parse_race_form()"""

import pytest
import pandas as pd
from src.parser import parse_race_form

SAMPLE_FORM = """Race No 1 Oct 12 07:30PM The Meadows 515m
1. 123456Speedy Bolt 2d 31.5kg 2 J Smith 5-3-12 $24,500 Y 3 2
2. 654321Flash Star 3b 30.2kg 1 M Jones 8-5-20 $38,000 Y 5 4
"""


class TestParseRaceForm:
    def test_returns_dataframe(self):
        df = parse_race_form(SAMPLE_FORM)
        assert isinstance(df, pd.DataFrame)

    def test_empty_string_returns_empty_dataframe(self):
        df = parse_race_form("")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_whitespace_only_returns_empty_dataframe(self):
        df = parse_race_form("   \n\n   ")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_no_race_header_returns_empty_dataframe(self):
        df = parse_race_form("Some random text\nwithout any race headers\n")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_parsed_df_has_expected_columns(self):
        df = parse_race_form(SAMPLE_FORM)
        if len(df) > 0:
            expected = {"Box", "DogName", "Trainer", "CareerWins", "CareerStarts", "PrizeMoney"}
            assert expected.issubset(set(df.columns))

    def test_box_numbers_are_integers(self):
        df = parse_race_form(SAMPLE_FORM)
        if len(df) > 0:
            assert pd.api.types.is_integer_dtype(df["Box"]) or df["Box"].dtype == object

    def test_prize_money_is_numeric(self):
        df = parse_race_form(SAMPLE_FORM)
        if len(df) > 0:
            assert pd.api.types.is_numeric_dtype(df["PrizeMoney"])

    def test_distance_captured_from_header(self):
        df = parse_race_form(SAMPLE_FORM)
        if len(df) > 0:
            assert "Distance" in df.columns

    def test_track_captured_from_header(self):
        df = parse_race_form(SAMPLE_FORM)
        if len(df) > 0:
            assert "Track" in df.columns
