"""Tests for update_results.py — mocks TAB API; no live network calls."""

import pytest
from unittest.mock import patch, MagicMock

from src.results_tracker import log_prediction, get_pending
import update_results as ur


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_results.db")
    monkeypatch.setenv("RESULTS_DB", db_file)
    yield db_file


def _seed(dog_name="Speedy", odds=4.0):
    log_prediction(
        meeting="The Meadows",
        race_number=1,
        date="2026-04-03",
        dog_name=dog_name,
        box=1,
        predicted_rank=1,
        composite_score=0.8,
        win_prob=0.25,
        odds_at_prediction=odds,
    )


class TestMatchDog:
    def test_exact_match(self):
        positions = {"SPEEDY": 1, "FLASH": 2}
        assert ur._match_dog("Speedy", positions) == 1

    def test_case_insensitive(self):
        positions = {"SPEEDY GONZALES": 1}
        assert ur._match_dog("speedy gonzales", positions) == 1

    def test_partial_match(self):
        positions = {"SPEEDY GONZALES": 1}
        assert ur._match_dog("Speedy", positions) == 1

    def test_no_match_returns_none(self):
        positions = {"FLASH": 2}
        assert ur._match_dog("Speedy", positions) is None


class TestFetchMeetingResults:
    def test_successful_response_parsed(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "runners": [
                {"runnerName": "SPEEDY", "finishingPosition": 1},
                {"runnerName": "FLASH", "finishingPosition": 2},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            result = ur.fetch_meeting_results("2026-04-03", "The Meadows", 1)
        assert result == {"SPEEDY": 1, "FLASH": 2}

    def test_network_error_returns_none(self):
        import requests
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            result = ur.fetch_meeting_results("2026-04-03", "The Meadows", 1)
        assert result is None

    def test_empty_runners_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"runners": []}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            result = ur.fetch_meeting_results("2026-04-03", "The Meadows", 1)
        assert result is None

    def test_non_json_response_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("no JSON")
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            result = ur.fetch_meeting_results("2026-04-03", "The Meadows", 1)
        assert result is None


class TestResolvePredictions:
    def test_no_pending_returns_zero(self):
        resolved, failed = ur.resolve_predictions()
        assert resolved == 0
        assert failed == 0

    def test_successful_resolution(self):
        _seed("Speedy")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "runners": [{"runnerName": "SPEEDY", "finishingPosition": 1}]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            resolved, failed = ur.resolve_predictions("2026-04-03")
        assert resolved == 1
        assert failed == 0
        assert get_pending() == []

    def test_api_failure_counts_as_failed(self):
        _seed("Speedy")
        import requests
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            resolved, failed = ur.resolve_predictions("2026-04-03")
        assert resolved == 0
        assert failed == 1
        assert len(get_pending()) == 1

    def test_dog_not_in_results_counts_as_failed(self):
        _seed("Speedy")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "runners": [{"runnerName": "OTHER DOG", "finishingPosition": 1}]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            resolved, failed = ur.resolve_predictions("2026-04-03")
        assert resolved == 0
        assert failed == 1
