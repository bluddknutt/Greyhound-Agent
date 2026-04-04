"""
Tests for results_tracker.py — SQLite-backed prediction logging and P&L analytics.
"""

import os
import tempfile
import pytest

from results_tracker import (
    log_prediction,
    update_result,
    get_summary,
    get_pending,
    _init_db,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a fresh temporary SQLite database."""
    db_path = str(tmp_path / "test_results.db")
    _init_db(db_path)
    return db_path


# ──────────────────────────────────────────
# log_prediction()
# ──────────────────────────────────────────

class TestLogPrediction:
    def test_returns_integer_race_id(self, tmp_db):
        rid = log_prediction(
            meeting="Sandown Park",
            race_number=3,
            date="2026-04-03",
            dog_name="Rapid Fire",
            predicted_rank=1,
            db_path=tmp_db,
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_increments_race_id(self, tmp_db):
        rid1 = log_prediction("Sandown Park", 3, "2026-04-03", "Dog A", 1, db_path=tmp_db)
        rid2 = log_prediction("Sandown Park", 3, "2026-04-03", "Dog B", 2, db_path=tmp_db)
        assert rid2 > rid1

    def test_stores_all_fields(self, tmp_db):
        import sqlite3
        log_prediction(
            meeting="Wentworth Park",
            race_number=5,
            date="2026-04-04",
            dog_name="Blaze Runner",
            predicted_rank=2,
            odds_at_prediction=4.50,
            stake=20.0,
            confidence_tier="high",
            db_path=tmp_db,
        )
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM predictions WHERE dog_name='Blaze Runner'").fetchone()
        conn.close()

        assert row["meeting"] == "Wentworth Park"
        assert row["race_number"] == 5
        assert row["date"] == "2026-04-04"
        assert row["predicted_rank"] == 2
        assert row["odds_at_prediction"] == pytest.approx(4.50)
        assert row["stake"] == pytest.approx(20.0)
        assert row["confidence_tier"] == "high"
        assert row["actual_result"] is None
        assert row["profit_loss"] is None

    def test_duplicate_insert_is_idempotent(self, tmp_db):
        """Inserting the same prediction twice should not raise and return same/valid id."""
        rid1 = log_prediction("Sandown Park", 1, "2026-04-03", "Dog X", 1, db_path=tmp_db)
        rid2 = log_prediction("Sandown Park", 1, "2026-04-03", "Dog X", 1, db_path=tmp_db)
        assert rid1 == rid2

    def test_default_stake_is_ten(self, tmp_db):
        import sqlite3
        log_prediction("Track", 1, "2026-04-04", "Dog D", 1, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT stake FROM predictions WHERE dog_name='Dog D'").fetchone()
        conn.close()
        assert row[0] == pytest.approx(10.0)

    def test_default_confidence_is_medium(self, tmp_db):
        import sqlite3
        log_prediction("Track", 1, "2026-04-04", "Dog E", 1, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT confidence_tier FROM predictions WHERE dog_name='Dog E'"
        ).fetchone()
        conn.close()
        assert row[0] == "medium"


# ──────────────────────────────────────────
# update_result()
# ──────────────────────────────────────────

class TestUpdateResult:
    def _seed(self, db, dog="Runner", rank=1, odds=3.0, stake=10.0):
        return log_prediction(
            meeting="Sandown Park", race_number=1, date="2026-04-03",
            dog_name=dog, predicted_rank=rank,
            odds_at_prediction=odds, stake=stake, db_path=db,
        )

    def test_sets_actual_result(self, tmp_db):
        import sqlite3
        rid = self._seed(tmp_db)
        update_result(rid, actual_result=1, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT actual_result FROM predictions WHERE race_id=?", (rid,)
        ).fetchone()
        conn.close()
        assert row[0] == 1

    def test_auto_pl_win_rank1(self, tmp_db):
        """Rank-1 prediction wins when finishes 1st: profit = stake * (odds - 1)."""
        import sqlite3
        rid = self._seed(tmp_db, rank=1, odds=4.0, stake=10.0)
        update_result(rid, actual_result=1, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT profit_loss FROM predictions WHERE race_id=?", (rid,)).fetchone()
        conn.close()
        assert row[0] == pytest.approx(30.0)   # 10 * (4 - 1)

    def test_auto_pl_loss_rank1(self, tmp_db):
        """Rank-1 prediction that finishes 4th loses the stake."""
        import sqlite3
        rid = self._seed(tmp_db, rank=1, odds=4.0, stake=10.0)
        update_result(rid, actual_result=4, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT profit_loss FROM predictions WHERE race_id=?", (rid,)).fetchone()
        conn.close()
        assert row[0] == pytest.approx(-10.0)

    def test_auto_pl_place_rank2(self, tmp_db):
        """Rank-2 prediction that finishes 3rd gets place payout."""
        import sqlite3
        rid = self._seed(tmp_db, dog="PlaceDog", rank=2, odds=8.0, stake=10.0)
        update_result(rid, actual_result=3, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT profit_loss FROM predictions WHERE race_id=?", (rid,)).fetchone()
        conn.close()
        # place_odds = 8/4 = 2.0; profit = 10 * (2.0 - 1) = 10
        assert row[0] == pytest.approx(10.0)

    def test_override_profit_loss(self, tmp_db):
        """Explicit profit_loss parameter overrides calculation."""
        import sqlite3
        rid = self._seed(tmp_db)
        update_result(rid, actual_result=2, profit_loss=99.99, db_path=tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT profit_loss FROM predictions WHERE race_id=?", (rid,)).fetchone()
        conn.close()
        assert row[0] == pytest.approx(99.99)

    def test_invalid_race_id_raises(self, tmp_db):
        with pytest.raises(ValueError, match="No prediction found"):
            update_result(9999, actual_result=1, db_path=tmp_db)


# ──────────────────────────────────────────
# get_pending()
# ──────────────────────────────────────────

class TestGetPending:
    def test_new_predictions_are_pending(self, tmp_db):
        log_prediction("Track A", 1, "2026-04-03", "Dog 1", 1, db_path=tmp_db)
        log_prediction("Track A", 1, "2026-04-03", "Dog 2", 2, db_path=tmp_db)
        pending = get_pending(tmp_db)
        assert len(pending) == 2

    def test_settled_not_in_pending(self, tmp_db):
        rid = log_prediction("Track A", 1, "2026-04-03", "Dog 1", 1, db_path=tmp_db)
        log_prediction("Track A", 1, "2026-04-03", "Dog 2", 2, db_path=tmp_db)
        update_result(rid, actual_result=1, db_path=tmp_db)
        pending = get_pending(tmp_db)
        assert len(pending) == 1
        assert pending[0]["dog_name"] == "Dog 2"

    def test_empty_db_returns_empty_list(self, tmp_db):
        assert get_pending(tmp_db) == []


# ──────────────────────────────────────────
# get_summary()
# ──────────────────────────────────────────

class TestGetSummary:
    def _seed_and_settle(self, db, meeting="M", race=1, date="2026-04-03",
                         dog="Dog", rank=1, odds=3.0, stake=10.0,
                         actual=1):
        rid = log_prediction(
            meeting=meeting, race_number=race, date=date, dog_name=dog,
            predicted_rank=rank, odds_at_prediction=odds, stake=stake,
            db_path=db,
        )
        if actual is not None:
            update_result(rid, actual_result=actual, db_path=db)
        return rid

    def test_empty_db_summary(self, tmp_db):
        s = get_summary(tmp_db)
        assert s["total_bets"] == 0
        assert s["settled_bets"] == 0
        assert s["win_rate"] == pytest.approx(0.0)
        assert s["roi_pct"] == pytest.approx(0.0)
        assert s["total_profit_loss"] == pytest.approx(0.0)
        assert s["streak"] == 0

    def test_counts_all_and_settled(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="Dog A", actual=1)
        log_prediction("M", 1, "2026-04-04", "Dog B", 2, db_path=tmp_db)  # unsettled
        s = get_summary(tmp_db)
        assert s["total_bets"] == 2
        assert s["settled_bets"] == 1

    def test_win_rate_all_wins(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", odds=3.0, stake=10.0, actual=1)
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=1)
        s = get_summary(tmp_db)
        assert s["win_rate"] == pytest.approx(1.0)

    def test_win_rate_all_losses(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", odds=3.0, stake=10.0, actual=5)
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=6)
        s = get_summary(tmp_db)
        assert s["win_rate"] == pytest.approx(0.0)

    def test_roi_positive_on_profitable_bets(self, tmp_db):
        # Win: profit = 10 * (3-1) = 20
        self._seed_and_settle(tmp_db, dog="A", odds=3.0, stake=10.0, actual=1)
        s = get_summary(tmp_db)
        assert s["roi_pct"] > 0

    def test_roi_negative_on_losses(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", odds=3.0, stake=10.0, actual=5)
        s = get_summary(tmp_db)
        assert s["roi_pct"] < 0

    def test_streak_consecutive_wins(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", race=1, odds=3.0, stake=10.0, actual=1)
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=1)
        self._seed_and_settle(tmp_db, dog="C", race=3, odds=3.0, stake=10.0, actual=1)
        s = get_summary(tmp_db)
        assert s["streak"] == 3

    def test_streak_consecutive_losses(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", race=1, odds=3.0, stake=10.0, actual=5)
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=6)
        s = get_summary(tmp_db)
        assert s["streak"] == -2

    def test_streak_resets_after_loss(self, tmp_db):
        self._seed_and_settle(tmp_db, dog="A", race=1, odds=3.0, stake=10.0, actual=1)
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=5)
        self._seed_and_settle(tmp_db, dog="C", race=3, odds=3.0, stake=10.0, actual=1)
        s = get_summary(tmp_db)
        # Most recent is a win, streak = 1
        assert s["streak"] == 1

    def test_by_confidence_breakdown(self, tmp_db):
        rid1 = log_prediction("M", 1, "2026-04-03", "Dog H", 1,
                               odds_at_prediction=3.0, stake=10.0,
                               confidence_tier="high", db_path=tmp_db)
        update_result(rid1, actual_result=1, db_path=tmp_db)

        rid2 = log_prediction("M", 2, "2026-04-03", "Dog L", 1,
                               odds_at_prediction=3.0, stake=10.0,
                               confidence_tier="low", db_path=tmp_db)
        update_result(rid2, actual_result=5, db_path=tmp_db)

        s = get_summary(tmp_db)
        assert "high" in s["by_confidence"]
        assert "low" in s["by_confidence"]
        assert s["by_confidence"]["high"]["win_rate"] == pytest.approx(1.0)
        assert s["by_confidence"]["low"]["win_rate"] == pytest.approx(0.0)

    def test_profit_loss_calculation(self, tmp_db):
        # 2 wins of $20 each, 1 loss of $10
        self._seed_and_settle(tmp_db, dog="A", race=1, odds=3.0, stake=10.0, actual=1)  # +20
        self._seed_and_settle(tmp_db, dog="B", race=2, odds=3.0, stake=10.0, actual=1)  # +20
        self._seed_and_settle(tmp_db, dog="C", race=3, odds=3.0, stake=10.0, actual=5)  # -10
        s = get_summary(tmp_db)
        assert s["total_profit_loss"] == pytest.approx(30.0)
        assert s["total_staked"] == pytest.approx(30.0)
