"""Tests for src/scorer.py — pure-function unit tests (no CSV I/O required)."""

import pytest
import numpy as np
import pandas as pd

from src.scorer import (
    safe_float,
    parse_placing,
    normalise,
    compute_form_score,
    compute_box_bias,
    generic_box_advantage,
    grade_to_num,
    compute_speed_rating,
    compute_track_fitness,
)


class TestSafeFloat:
    def test_empty_string_returns_nan(self):
        assert np.isnan(safe_float(""))

    def test_nbt_returns_nan(self):
        assert np.isnan(safe_float("NBT"))

    def test_nan_returns_nan(self):
        assert np.isnan(safe_float(np.nan))

    def test_valid_string_returns_float(self):
        assert safe_float("29.5") == pytest.approx(29.5)

    def test_dollar_sign_stripped(self):
        assert safe_float("$12.50") == pytest.approx(12.50)

    def test_kg_suffix_stripped(self):
        assert safe_float("31.5kg") == pytest.approx(31.5)

    def test_default_returned_on_none(self):
        assert safe_float(None, default=0.0) == 0.0

    def test_integer_input(self):
        assert safe_float(42) == pytest.approx(42.0)


class TestParsePlacing:
    def test_valid_placing_parsed(self):
        pos, field = parse_placing("3rd/8")
        assert pos == 3
        assert field == 8

    def test_first_place_parsed(self):
        pos, field = parse_placing("1st/8")
        assert pos == 1
        assert field == 8

    def test_second_place_parsed(self):
        pos, field = parse_placing("2nd/10")
        assert pos == 2
        assert field == 10

    def test_none_returns_nan_tuple(self):
        pos, field = parse_placing(None)
        assert np.isnan(pos)
        assert np.isnan(field)

    def test_invalid_string_returns_nan_tuple(self):
        pos, field = parse_placing("not-a-placing")
        assert np.isnan(pos)
        assert np.isnan(field)

    def test_nan_returns_nan_tuple(self):
        pos, field = parse_placing(np.nan)
        assert np.isnan(pos)
        assert np.isnan(field)


class TestNormalise:
    def test_uniform_series_returns_half(self):
        s = pd.Series([5.0, 5.0, 5.0])
        result = normalise(s)
        assert all(result == 0.5)

    def test_min_maps_to_zero(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = normalise(s)
        assert result.iloc[0] == pytest.approx(0.0)

    def test_max_maps_to_one(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = normalise(s)
        assert result.iloc[-1] == pytest.approx(1.0)

    def test_output_length_matches_input(self):
        s = pd.Series([10.0, 20.0, 30.0, 40.0])
        result = normalise(s)
        assert len(result) == len(s)


class TestComputeFormScore:
    def test_no_data_returns_half(self):
        row = {}
        assert compute_form_score(row) == pytest.approx(0.5)

    def test_all_wins_returns_high_score(self):
        row = {f"pr{i}_placing": "1st/8" for i in range(1, 7)}
        score = compute_form_score(row)
        assert score > 0.8

    def test_all_last_returns_low_score(self):
        row = {f"pr{i}_placing": "8th/8" for i in range(1, 7)}
        score = compute_form_score(row)
        assert score < 0.2

    def test_fallback_to_last_4_starts_string(self):
        row = {"last_4_starts": "1122"}
        score = compute_form_score(row)
        assert 0 < score <= 1.0


class TestComputeBoxBias:
    def test_no_box_data_uses_generic(self):
        row = {"box": 1, "box_starts": 0, "box_win_pct": 0, "box_place_pct": 0, "distance": "515m"}
        result = compute_box_bias(row)
        assert 0 <= result <= 1.0

    def test_high_win_pct_returns_high_score(self):
        row = {"box": 1, "box_starts": 10, "box_win_pct": 80, "box_place_pct": 90, "distance": "515m"}
        result = compute_box_bias(row)
        assert result > 0.5

    def test_zero_win_pct_returns_low_score(self):
        row = {"box": 1, "box_starts": 10, "box_win_pct": 0, "box_place_pct": 0, "distance": "515m"}
        result = compute_box_bias(row)
        assert result == pytest.approx(0.0)


class TestGenericBoxAdvantage:
    def test_box_1_sprint_has_highest_advantage(self):
        adv_box1 = generic_box_advantage(1, 300)
        adv_box6 = generic_box_advantage(6, 300)
        assert adv_box1 > adv_box6

    def test_unknown_box_returns_default(self):
        result = generic_box_advantage(99, 400)
        assert result == pytest.approx(0.08)

    def test_all_distances_return_valid_float(self):
        for dist in [300, 400, 600]:
            for box in range(1, 9):
                result = generic_box_advantage(box, dist)
                assert 0 < result <= 1.0


class TestGradeToNum:
    def test_maiden_maps_to_1(self):
        assert grade_to_num("M") == 1

    def test_ffa_maps_to_7(self):
        assert grade_to_num("FFA") == 7

    def test_none_returns_neutral(self):
        assert grade_to_num(None) == 5

    def test_numeric_string_parsed(self):
        assert grade_to_num("3") == 4


class TestComputeSpeedRating:
    def test_no_data_with_best_time_uses_fallback(self):
        row = {"best_time": "29.5"}
        rating = compute_speed_rating(row, 515)
        assert not np.isnan(rating)

    def test_no_data_no_best_time_returns_nan(self):
        row = {}
        rating = compute_speed_rating(row, 515)
        assert np.isnan(rating)

    def test_faster_dog_gets_higher_rating(self):
        fast = {"pr1_time": "29.0", "pr1_win_time": "29.0", "pr1_dist": "515"}
        slow = {"pr1_time": "31.0", "pr1_win_time": "29.0", "pr1_dist": "515"}
        assert compute_speed_rating(fast, 515) > compute_speed_rating(slow, 515)


class TestComputeTrackFitness:
    def test_returns_value_between_0_and_1(self):
        row = {"best_time": "29.5"}
        result = compute_track_fitness(row, 515)
        assert 0 <= result <= 1.0

    def test_no_data_returns_default(self):
        row = {}
        result = compute_track_fitness(row, 515)
        assert result == pytest.approx(0.5)

    def test_track_best_time_used_preferentially(self):
        row = {"track_best_time": "29.5", "best_time": "31.0"}
        result_with_track = compute_track_fitness(row, 515)
        row2 = {"best_time": "31.0"}
        result_without_track = compute_track_fitness(row2, 515)
        # Having a track best time should produce a different result than falling back to best_time
        assert result_with_track != result_without_track
