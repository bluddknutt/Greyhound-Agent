"""
Tests for dashboard.py — terminal P&L summary formatting and data aggregation.
"""

import pytest
from datetime import datetime, timedelta

import results_tracker as rt
import dashboard


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "dash_test.db")
    rt._init_db(db_path)
    return db_path


def _seed(db, meeting="Sandown Park", race=1, date="2026-04-03",
          dog="Dog", rank=1, odds=3.0, stake=10.0, actual=None,
          tier="medium"):
    rid = rt.log_prediction(
        meeting=meeting, race_number=race, date=date,
        dog_name=dog, predicted_rank=rank,
        odds_at_prediction=odds, stake=stake,
        confidence_tier=tier, db_path=db,
    )
    if actual is not None:
        rt.update_result(rid, actual_result=actual, db_path=db)
    return rid


# ──────────────────────────────────────────
# _pl_stats
# ──────────────────────────────────────────

class TestPlStats:
    def test_empty_rows_returns_zeros(self):
        stats = dashboard._pl_stats([])
        assert stats["bets"] == 0
        assert stats["profit_loss"] == pytest.approx(0.0)
        assert stats["win_rate"] == pytest.approx(0.0)
        assert stats["roi_pct"] == pytest.approx(0.0)

    def test_single_win(self):
        rows = [{"profit_loss": 20.0, "stake": 10.0}]
        stats = dashboard._pl_stats(rows)
        assert stats["bets"] == 1
        assert stats["wins"] == 1
        assert stats["profit_loss"] == pytest.approx(20.0)
        assert stats["win_rate"] == pytest.approx(1.0)
        assert stats["roi_pct"] == pytest.approx(200.0)

    def test_single_loss(self):
        rows = [{"profit_loss": -10.0, "stake": 10.0}]
        stats = dashboard._pl_stats(rows)
        assert stats["wins"] == 0
        assert stats["win_rate"] == pytest.approx(0.0)
        assert stats["roi_pct"] == pytest.approx(-100.0)

    def test_mixed_results(self):
        rows = [
            {"profit_loss": 20.0, "stake": 10.0},
            {"profit_loss": -10.0, "stake": 10.0},
        ]
        stats = dashboard._pl_stats(rows)
        assert stats["bets"] == 2
        assert stats["wins"] == 1
        assert stats["profit_loss"] == pytest.approx(10.0)
        assert stats["win_rate"] == pytest.approx(0.5)
        assert stats["roi_pct"] == pytest.approx(50.0)


# ──────────────────────────────────────────
# _last_n_days
# ──────────────────────────────────────────

class TestLastNDays:
    def _make_row(self, date_str):
        return {"date": date_str, "profit_loss": 10.0, "stake": 10.0}

    def test_includes_recent_rows(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        rows = [self._make_row(today)]
        result = dashboard._last_n_days(rows, 7)
        assert len(result) == 1

    def test_excludes_old_rows(self):
        old_date = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        rows = [self._make_row(old_date)]
        result = dashboard._last_n_days(rows, 7)
        assert len(result) == 0

    def test_mixed_dates(self):
        recent = datetime.utcnow().strftime("%Y-%m-%d")
        old = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        rows = [self._make_row(recent), self._make_row(old)]
        result = dashboard._last_n_days(rows, 7)
        assert len(result) == 1


# ──────────────────────────────────────────
# _meeting_breakdown
# ──────────────────────────────────────────

class TestMeetingBreakdown:
    def test_groups_by_meeting(self):
        rows = [
            {"meeting": "Track A", "profit_loss": 20.0, "stake": 10.0},
            {"meeting": "Track A", "profit_loss": -10.0, "stake": 10.0},
            {"meeting": "Track B", "profit_loss": 5.0, "stake": 10.0},
        ]
        result = dashboard._meeting_breakdown(rows)
        meetings = {r["meeting"] for r in result}
        assert meetings == {"Track A", "Track B"}

    def test_sorted_by_profit_descending(self):
        rows = [
            {"meeting": "Poor Track", "profit_loss": -50.0, "stake": 10.0},
            {"meeting": "Good Track", "profit_loss": 100.0, "stake": 10.0},
        ]
        result = dashboard._meeting_breakdown(rows)
        assert result[0]["meeting"] == "Good Track"
        assert result[-1]["meeting"] == "Poor Track"

    def test_roi_calculated(self):
        rows = [{"meeting": "Track", "profit_loss": 10.0, "stake": 10.0}]
        result = dashboard._meeting_breakdown(rows)
        assert result[0]["roi_pct"] == pytest.approx(100.0)

    def test_empty_rows_returns_empty(self):
        assert dashboard._meeting_breakdown([]) == []


# ──────────────────────────────────────────
# print_dashboard (smoke test)
# ──────────────────────────────────────────

class TestPrintDashboard:
    def test_runs_on_empty_db(self, tmp_db, capsys):
        dashboard.print_dashboard(tmp_db)
        out = capsys.readouterr().out
        assert "GREYHOUND PREDICTION DASHBOARD" in out
        assert "No settled predictions" in out

    def test_runs_with_data(self, tmp_db, capsys):
        _seed(tmp_db, dog="Alpha", race=1, odds=3.0, actual=1, tier="high")
        _seed(tmp_db, dog="Beta", race=2, odds=5.0, actual=4, tier="low")
        dashboard.print_dashboard(tmp_db)
        out = capsys.readouterr().out
        assert "ALL-TIME" in out
        assert "CONFIDENCE TIER" in out
        assert "MEETINGS" in out

    def test_shows_streak_on_consecutive_wins(self, tmp_db, capsys):
        _seed(tmp_db, dog="A", race=1, odds=3.0, actual=1, tier="high")
        _seed(tmp_db, dog="B", race=2, odds=3.0, actual=1, tier="high")
        dashboard.print_dashboard(tmp_db)
        out = capsys.readouterr().out
        assert "streak" in out.lower()

    def test_shows_best_and_worst_meeting(self, tmp_db, capsys):
        _seed(tmp_db, meeting="Good Track", dog="W", race=1, odds=4.0, actual=1)
        _seed(tmp_db, meeting="Bad Track", dog="L", race=1, odds=4.0, actual=5)
        dashboard.print_dashboard(tmp_db)
        out = capsys.readouterr().out
        assert "Good Track" in out
        assert "Bad Track" in out
