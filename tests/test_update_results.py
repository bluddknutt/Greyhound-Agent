"""
Tests for update_results.py — TAB API fetching and result matching logic.
"""

import pytest
from unittest.mock import patch, MagicMock

import update_results as ur


# ──────────────────────────────────────────
# _normalise_name
# ──────────────────────────────────────────

class TestNormaliseName:
    def test_lowercases(self):
        assert ur._normalise_name("RAPID FIRE") == "rapid fire"

    def test_strips_whitespace(self):
        assert ur._normalise_name("  Dog Name  ") == "dog name"

    def test_removes_apostrophe(self):
        assert ur._normalise_name("O'Brien") == "obrien"

    def test_replaces_hyphens_with_space(self):
        assert ur._normalise_name("Turbo-Charged") == "turbo charged"


# ──────────────────────────────────────────
# find_finishing_position
# ──────────────────────────────────────────

class TestFindFinishingPosition:
    def _make_result(self, runners):
        return {"runners": runners}

    def test_exact_name_match(self):
        data = self._make_result([
            {"runnerName": "Rapid Fire", "finishingPosition": 1},
            {"runnerName": "Blaze Runner", "finishingPosition": 2},
        ])
        assert ur.find_finishing_position(data, "Rapid Fire") == 1

    def test_case_insensitive_match(self):
        data = self._make_result([
            {"runnerName": "rapid fire", "finishingPosition": 3},
        ])
        assert ur.find_finishing_position(data, "RAPID FIRE") == 3

    def test_partial_match_fallback(self):
        data = self._make_result([
            {"runnerName": "Rapid Fire Star", "finishingPosition": 2},
        ])
        # "Rapid Fire" is substring of "Rapid Fire Star"
        assert ur.find_finishing_position(data, "Rapid Fire") == 2

    def test_returns_none_when_not_found(self):
        data = self._make_result([
            {"runnerName": "Unknown Dog", "finishingPosition": 1},
        ])
        assert ur.find_finishing_position(data, "Different Dog") is None

    def test_none_result_data_returns_none(self):
        assert ur.find_finishing_position(None, "Any Dog") is None

    def test_empty_runners_returns_none(self):
        assert ur.find_finishing_position({"runners": []}, "Any Dog") is None

    def test_non_integer_position_returns_none(self):
        data = self._make_result([
            {"runnerName": "Dog", "finishingPosition": "DNS"},
        ])
        assert ur.find_finishing_position(data, "Dog") is None

    def test_integer_position_as_string(self):
        data = self._make_result([
            {"runnerName": "Dog", "finishingPosition": "4"},
        ])
        assert ur.find_finishing_position(data, "Dog") == 4


# ──────────────────────────────────────────
# _find_meeting_code
# ──────────────────────────────────────────

class TestFindMeetingCode:
    def _meetings(self):
        return [
            {"meetingName": "Sandown Park", "meetingCode": "SAN", "raceType": "G"},
            {"meetingName": "Wentworth Park", "meetingCode": "WP", "raceType": "G"},
            {"meetingName": "The Meadows", "meetingCode": "MEA", "raceType": "G"},
        ]

    def test_exact_match(self):
        assert ur._find_meeting_code(self._meetings(), "Sandown Park") == "SAN"

    def test_case_insensitive_match(self):
        assert ur._find_meeting_code(self._meetings(), "sandown park") == "SAN"

    def test_partial_match(self):
        assert ur._find_meeting_code(self._meetings(), "Meadows") == "MEA"

    def test_no_match_returns_none(self):
        assert ur._find_meeting_code(self._meetings(), "Unknown Venue") is None

    def test_empty_meetings_returns_none(self):
        assert ur._find_meeting_code([], "Sandown Park") is None


# ──────────────────────────────────────────
# fetch_meetings (mocked HTTP)
# ──────────────────────────────────────────

class TestFetchMeetings:
    def test_returns_greyhound_meetings_only(self):
        mock_data = {
            "meetings": [
                {"meetingName": "Sandown Park", "meetingCode": "SAN", "raceType": "G"},
                {"meetingName": "Flemington", "meetingCode": "FLE", "raceType": "R"},
                {"meetingName": "Wentworth Park", "meetingCode": "WP", "raceType": "GREYHOUND"},
            ]
        }
        with patch("update_results._get", return_value=mock_data):
            meetings = ur.fetch_meetings("2026-04-03")
        assert len(meetings) == 2
        assert all(m["raceType"].upper() in ("G", "GREYHOUND", "GH") for m in meetings)

    def test_api_failure_returns_empty(self):
        with patch("update_results._get", return_value=None):
            meetings = ur.fetch_meetings("2026-04-03")
        assert meetings == []

    def test_empty_meetings_key(self):
        with patch("update_results._get", return_value={"meetings": []}):
            meetings = ur.fetch_meetings("2026-04-03")
        assert meetings == []


# ──────────────────────────────────────────
# update_for_date (integration-style with mocks)
# ──────────────────────────────────────────

class TestUpdateForDate:
    def _make_pending(self, meeting="Sandown Park", race=1, date="2026-04-03", dog="Dog A"):
        return [{
            "race_id": 1,
            "meeting": meeting,
            "race_number": race,
            "date": date,
            "dog_name": dog,
            "predicted_rank": 1,
            "odds_at_prediction": 3.0,
            "stake": 10.0,
            "confidence_tier": "high",
        }]

    def test_updates_on_successful_fetch(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import results_tracker as rt
        rt._init_db(db_path)
        rt.log_prediction(
            "Sandown Park", 1, "2026-04-03", "Dog A", 1,
            odds_at_prediction=3.0, stake=10.0, db_path=db_path
        )

        mock_meetings = [{"meetingName": "Sandown Park", "meetingCode": "SAN", "raceType": "G"}]
        mock_results = {"runners": [{"runnerName": "Dog A", "finishingPosition": 1}]}

        with patch("update_results.fetch_meetings", return_value=mock_meetings), \
             patch("update_results.fetch_race_results", return_value=mock_results), \
             patch("update_results.get_pending", return_value=self._make_pending()):
            updated = ur.update_for_date("2026-04-03", dry_run=True)

        assert updated == 1

    def test_skips_when_no_meetings(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("update_results.fetch_meetings", return_value=[]):
            updated = ur.update_for_date("2026-04-03")
        assert updated == 0

    def test_skips_when_no_pending(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with patch("update_results.get_pending", return_value=[]):
            updated = ur.update_for_date("2026-04-03")
        assert updated == 0
