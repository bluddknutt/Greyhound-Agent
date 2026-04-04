"""Tests for dashboard.py — checks formatted output and argument parsing."""

import pytest
from unittest.mock import patch
from io import StringIO

from src.results_tracker import log_prediction, update_result
import dashboard


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_results.db")
    monkeypatch.setenv("RESULTS_DB", db_file)
    yield db_file


def _seed_resolved(dog="Speedy", pos=1, odds=4.0, meeting="The Meadows"):
    log_prediction(
        meeting=meeting, race_number=1, date="2026-04-03",
        dog_name=dog, box=1, predicted_rank=1,
        composite_score=0.8, win_prob=0.25, odds_at_prediction=odds,
    )
    update_result(meeting, 1, "2026-04-03", dog, pos)


class TestPrintSummary:
    def test_no_error_on_empty_db(self, capsys):
        from src.results_tracker import get_summary
        summary = get_summary()
        dashboard.print_summary("Test", summary)  # should not raise
        out = capsys.readouterr().out
        assert "Test" in out

    def test_win_data_shown(self, capsys):
        _seed_resolved("Speedy", pos=1, odds=4.0)
        from src.results_tracker import get_summary
        summary = get_summary()
        dashboard.print_summary("All-Time", summary)
        out = capsys.readouterr().out
        assert "Wins" in out
        assert "P&L" in out

    def test_tier_breakdown_shown_when_data_exists(self, capsys):
        _seed_resolved("Speedy", pos=1, odds=4.0)
        from src.results_tracker import get_summary
        summary = get_summary()
        dashboard.print_summary("Test", summary)
        out = capsys.readouterr().out
        assert "Tier" in out

    def test_meeting_breakdown_shown(self, capsys):
        _seed_resolved("Speedy", pos=2, odds=4.0, meeting="The Meadows")
        from src.results_tracker import get_summary
        summary = get_summary()
        dashboard.print_summary("Test", summary)
        out = capsys.readouterr().out
        assert "The Meadows" in out

    def test_streak_shown_when_wins(self, capsys):
        _seed_resolved("Speedy", pos=1)
        from src.results_tracker import get_summary
        summary = get_summary()
        dashboard.print_summary("Test", summary)
        out = capsys.readouterr().out
        assert "streak" in out.lower() or "win" in out.lower()


class TestMainFunction:
    def test_main_runs_without_error(self, capsys):
        _seed_resolved()
        with patch("sys.argv", ["dashboard.py"]):
            dashboard.main()
        out = capsys.readouterr().out
        assert len(out) > 0

    def test_all_time_flag(self, capsys):
        _seed_resolved()
        with patch("sys.argv", ["dashboard.py", "--all"]):
            dashboard.main()
        out = capsys.readouterr().out
        assert "All-Time" in out

    def test_custom_days_flag(self, capsys):
        _seed_resolved()
        with patch("sys.argv", ["dashboard.py", "--days", "30"]):
            dashboard.main()
        out = capsys.readouterr().out
        assert "30" in out
