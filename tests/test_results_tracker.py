"""Tests for src/results_tracker.py — all DB operations use a temp SQLite file."""

import os
import pytest

from src.results_tracker import (
    log_prediction,
    update_result,
    get_pending,
    get_summary,
    _make_race_id,
    _confidence_tier,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a fresh temp database."""
    db_file = str(tmp_path / "test_results.db")
    monkeypatch.setenv("RESULTS_DB", db_file)
    yield db_file


# ── _make_race_id ────────────────────────────────────────────


class TestMakeRaceId:
    def test_spaces_become_hyphens(self):
        rid = _make_race_id("The Meadows", 1, "2026-04-03")
        assert rid == "the-meadows_1_2026-04-03"

    def test_already_lowercase(self):
        rid = _make_race_id("sandown park", 3, "2026-04-03")
        assert rid == "sandown-park_3_2026-04-03"

    def test_underscores_become_hyphens(self):
        rid = _make_race_id("the_meadows", 2, "2026-04-03")
        assert rid == "the-meadows_2_2026-04-03"


# ── _confidence_tier ─────────────────────────────────────────


class TestConfidenceTier:
    def test_tier1_rank1_high_prob(self):
        assert _confidence_tier(1, 0.35) == "Tier 1"

    def test_tier1_boundary(self):
        assert _confidence_tier(1, 0.30) == "Tier 1"

    def test_tier2_rank1_medium_prob(self):
        assert _confidence_tier(1, 0.25) == "Tier 2"

    def test_tier2_rank2_high_prob(self):
        assert _confidence_tier(2, 0.25) == "Tier 2"

    def test_tier3_rank1_low_prob(self):
        assert _confidence_tier(1, 0.15) == "Tier 3"

    def test_tier3_rank2_low_prob(self):
        assert _confidence_tier(2, 0.10) == "Tier 3"

    def test_tier4_rank3(self):
        assert _confidence_tier(3, 0.20) == "Tier 4"

    def test_tier4_rank4(self):
        assert _confidence_tier(4, 0.10) == "Tier 4"


# ── log_prediction ───────────────────────────────────────────


class TestLogPrediction:
    def _log(self, **kwargs):
        defaults = dict(
            meeting="The Meadows",
            race_number=1,
            date="2026-04-03",
            dog_name="Speedy",
            box=1,
            predicted_rank=1,
            composite_score=0.85,
            win_prob=0.32,
            odds_at_prediction=3.125,
        )
        defaults.update(kwargs)
        return log_prediction(**defaults)

    def test_returns_row_id_on_first_insert(self):
        row_id = self._log()
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_returns_none_on_duplicate(self):
        self._log()
        row_id2 = self._log()
        assert row_id2 is None

    def test_different_dog_same_race_both_logged(self):
        id1 = self._log(dog_name="Speedy")
        id2 = self._log(dog_name="Flash")
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

    def test_prediction_appears_in_pending(self):
        self._log()
        pending = get_pending()
        assert len(pending) == 1
        assert pending[0]["dog_name"] == "Speedy"

    def test_confidence_tier_assigned(self):
        self._log(predicted_rank=1, win_prob=0.32)
        pending = get_pending()
        assert pending[0]["confidence_tier"] == "Tier 1"


# ── update_result ────────────────────────────────────────────


class TestUpdateResult:
    def _setup(self, dog="Speedy", odds=4.0, stake=10.0):
        log_prediction(
            meeting="The Meadows",
            race_number=1,
            date="2026-04-03",
            dog_name=dog,
            box=1,
            predicted_rank=1,
            composite_score=0.80,
            win_prob=0.25,
            odds_at_prediction=odds,
            stake=stake,
        )

    def test_win_profit_correct(self):
        self._setup(odds=4.0, stake=10.0)
        ok = update_result("The Meadows", 1, "2026-04-03", "Speedy", 1)
        assert ok is True
        pending = get_pending()
        assert len(pending) == 0  # resolved

    def test_loss_profit_is_negative_stake(self):
        self._setup(odds=4.0, stake=10.0)
        update_result("The Meadows", 1, "2026-04-03", "Speedy", 3)
        summary = get_summary()
        assert summary["total_profit_loss"] == pytest.approx(-10.0)

    def test_win_profit_is_stake_times_odds_minus_one(self):
        self._setup(odds=5.0, stake=10.0)
        update_result("The Meadows", 1, "2026-04-03", "Speedy", 1)
        summary = get_summary()
        # profit = 10 * (5 - 1) = 40
        assert summary["total_profit_loss"] == pytest.approx(40.0)

    def test_returns_false_for_unknown_dog(self):
        self._setup()
        ok = update_result("The Meadows", 1, "2026-04-03", "Unknown Dog", 1)
        assert ok is False


# ── get_pending ──────────────────────────────────────────────


class TestGetPending:
    def test_empty_db_returns_empty_list(self):
        assert get_pending() == []

    def test_date_filter_works(self):
        log_prediction(
            meeting="The Meadows", race_number=1, date="2026-04-03",
            dog_name="A", box=1, predicted_rank=1,
            composite_score=0.8, win_prob=0.25, odds_at_prediction=4.0,
        )
        log_prediction(
            meeting="Sandown Park", race_number=2, date="2026-04-04",
            dog_name="B", box=2, predicted_rank=2,
            composite_score=0.7, win_prob=0.20, odds_at_prediction=5.0,
        )
        result = get_pending(date="2026-04-03")
        assert len(result) == 1
        assert result[0]["dog_name"] == "A"

    def test_resolved_prediction_not_in_pending(self):
        log_prediction(
            meeting="The Meadows", race_number=1, date="2026-04-03",
            dog_name="Speedy", box=1, predicted_rank=1,
            composite_score=0.8, win_prob=0.30, odds_at_prediction=3.33,
        )
        update_result("The Meadows", 1, "2026-04-03", "Speedy", 2)
        assert get_pending() == []


# ── get_summary ──────────────────────────────────────────────


class TestGetSummary:
    def test_empty_db_returns_zeros(self):
        s = get_summary()
        assert s["total_bets"] == 0
        assert s["settled_bets"] == 0
        assert s["roi_pct"] == 0.0

    def test_win_rate_correct(self):
        for dog, pos in [("A", 1), ("B", 2), ("C", 3), ("D", 1)]:
            log_prediction(
                meeting="The Meadows", race_number=1, date="2026-04-03",
                dog_name=dog, box=1, predicted_rank=1,
                composite_score=0.8, win_prob=0.25, odds_at_prediction=4.0,
            )
            update_result("The Meadows", 1, "2026-04-03", dog, pos)
        s = get_summary()
        assert s["win_count"] == 2
        assert s["win_rate_pct"] == pytest.approx(50.0)

    def test_roi_positive_when_profitable(self):
        log_prediction(
            meeting="The Meadows", race_number=1, date="2026-04-03",
            dog_name="Speedy", box=1, predicted_rank=1,
            composite_score=0.8, win_prob=0.25, odds_at_prediction=6.0,
            stake=10.0,
        )
        update_result("The Meadows", 1, "2026-04-03", "Speedy", 1)
        s = get_summary()
        # profit = 10*(6-1) = 50 on 10 staked → ROI = 500%
        assert s["roi_pct"] > 0

    def test_by_tier_populated(self):
        log_prediction(
            meeting="The Meadows", race_number=1, date="2026-04-03",
            dog_name="Speedy", box=1, predicted_rank=1,
            composite_score=0.8, win_prob=0.35, odds_at_prediction=3.0,
        )
        update_result("The Meadows", 1, "2026-04-03", "Speedy", 1)
        s = get_summary()
        assert "Tier 1" in s["by_tier"]

    def test_streak_win(self):
        for i, dog in enumerate(["A", "B", "C"], start=1):
            log_prediction(
                meeting="The Meadows", race_number=i, date="2026-04-03",
                dog_name=dog, box=1, predicted_rank=1,
                composite_score=0.8, win_prob=0.25, odds_at_prediction=4.0,
            )
            update_result("The Meadows", i, "2026-04-03", dog, 1)
        s = get_summary()
        assert s["streak_type"] == "win"
        assert s["current_streak"] == 3
