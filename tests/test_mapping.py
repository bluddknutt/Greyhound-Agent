"""
Tests for src/mapping.py

Validates the integrity of the static track and timeslot data used throughout
the FastTrack API integration.
"""

import pytest
import mapping


REQUIRED_TRACK_KEYS = {'trackCode', 'trackName', 'State'}
VALID_STATES = {'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NZ'}
EXPECTED_TIMESLOTS = {'Twilight', 'Morning', 'Day', 'Night'}
EXPECTED_TIMESLOT_CODES = {'t', 'm', 'd', 'n'}


class TestTrackCodes:
    def test_track_codes_is_non_empty_list(self):
        assert isinstance(mapping.trackCodes, list)
        assert len(mapping.trackCodes) > 0

    def test_all_entries_have_required_keys(self):
        for entry in mapping.trackCodes:
            missing = REQUIRED_TRACK_KEYS - entry.keys()
            assert not missing, f"Entry {entry} is missing keys: {missing}"

    def test_track_code_values_are_integers(self):
        for entry in mapping.trackCodes:
            assert isinstance(entry['trackCode'], int), (
                f"trackCode for '{entry['trackName']}' is not an int: {entry['trackCode']!r}"
            )

    def test_track_names_are_non_empty_strings(self):
        for entry in mapping.trackCodes:
            assert isinstance(entry['trackName'], str) and entry['trackName'].strip(), (
                f"trackName is empty or not a string: {entry!r}"
            )

    def test_all_states_are_valid(self):
        invalid = [
            entry for entry in mapping.trackCodes
            if entry['State'] not in VALID_STATES
        ]
        assert not invalid, f"Entries with invalid states: {invalid}"

    def test_track_codes_are_unique(self):
        codes = [entry['trackCode'] for entry in mapping.trackCodes]
        duplicates = [c for c in set(codes) if codes.count(c) > 1]
        assert not duplicates, f"Duplicate trackCodes found: {duplicates}"

    def test_all_australian_states_represented(self):
        states_present = {entry['State'] for entry in mapping.trackCodes}
        au_states = {'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT'}
        missing = au_states - states_present
        assert not missing, f"Australian states missing from trackCodes: {missing}"


class TestTimeslotMapping:
    def test_timeslot_mapping_is_dict(self):
        assert isinstance(mapping.timeslot_mapping, dict)

    def test_all_expected_timeslots_present(self):
        assert set(mapping.timeslot_mapping.keys()) == EXPECTED_TIMESLOTS

    def test_timeslot_codes_are_single_chars(self):
        for name, code in mapping.timeslot_mapping.items():
            assert isinstance(code, str) and len(code) == 1, (
                f"Timeslot '{name}' has invalid code: {code!r}"
            )

    def test_timeslot_codes_are_unique(self):
        codes = list(mapping.timeslot_mapping.values())
        assert len(codes) == len(set(codes)), "Timeslot codes are not unique"

    def test_timeslot_codes_match_expected_values(self):
        assert set(mapping.timeslot_mapping.values()) == EXPECTED_TIMESLOT_CODES
