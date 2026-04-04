"""
Tests for src/fasttrack.py

All HTTP calls are mocked via unittest.mock so no live API key is required.
time.sleep is also patched to keep tests fast.
"""

import io
import pytest
from unittest.mock import patch, MagicMock, call
import pandas as pd

import fasttrack
from fasttrack import xmldict, Fasttrack
import mapping


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_urlopen_response(content: bytes):
    """Return a mock file-like object that urlopen would return."""
    mock_file = MagicMock()
    mock_file.read.return_value = content
    mock_file.__enter__ = lambda s: s
    mock_file.__exit__ = MagicMock(return_value=False)
    return mock_file


VALID_KEY_XML = b"""<?xml version="1.0"?>
<meetings><meeting track="300" timeslot="Night" date="01-Jan-2021"/></meetings>
"""

INVALID_KEY_XML = b"""<?xml version="1.0"?>
<exception>Invalid Security Key</exception>
"""

INVALID_DATE_XML = b"""<?xml version="1.0"?>
<exception>Invalid Date Specified</exception>
"""

MEETING_SINGLE_XML = b"""<?xml version="1.0"?>
<meetings>
  <meeting track="300" timeslot="Night" date="01-Jan-2021"/>
</meetings>
"""

MEETING_MULTI_XML = b"""<?xml version="1.0"?>
<meetings>
  <meeting track="300" timeslot="Night" date="01-Jan-2021"/>
  <meeting track="301" timeslot="Day" date="01-Jan-2021"/>
</meetings>
"""

FILE_NOT_FOUND_XML = b"""<?xml version="1.0"?>
<exception>File Not Found</exception>
"""

RACE_RESULTS_XML = b"""<?xml version="1.0"?>
<Meet>
  <Track>300</Track>
  <Date>01-Jan-2021</Date>
  <Race id="1">
    <Dog id="dog1">
      <BestTime>29.50</BestTime>
      <Trainer id="t1">John Smith</Trainer>
      <Dividends/>
      <Times/>
    </Dog>
    <Dog id="">
      <BestTime>* * * VACANT BOX * * *</BestTime>
      <Trainer id=""/>
    </Dog>
    <Dividends/>
    <Exotics/>
    <Times/>
  </Race>
</Meet>
"""

BASIC_FORMAT_MULTI_RACE_XML = b"""<?xml version="1.0"?>
<Meet>
  <Track>300</Track>
  <Date>01-Jan-2021</Date>
  <Quali>Y</Quali>
  <Race id="r1">
    <TipsComments><Bet>Bet1</Bet><Tips>Tip1</Tips></TipsComments>
    <Dog id="d1">
      <BestTime>29.50</BestTime>
      <Dam id="dam1">DamName</Dam>
      <Sire id="sire1">SireName</Sire>
      <Trainer id="tr1">TrainerName</Trainer>
    </Dog>
    <Dog id="d2">
      <BestTime>* * * VACANT BOX * * *</BestTime>
      <Dam id=""/>
      <Sire id=""/>
      <Trainer id=""/>
    </Dog>
  </Race>
  <Race id="r2">
    <TipsComments><Bet>Bet2</Bet><Tips>Tip2</Tips></TipsComments>
    <Dog id="d3">
      <BestTime>30.10</BestTime>
      <Dam id="dam3">DamName3</Dam>
      <Sire id="sire3">SireName3</Sire>
      <Trainer id="tr3">TrainerName3</Trainer>
    </Dog>
    <Dog id="d4">
      <BestTime>30.20</BestTime>
      <Dam id="dam4">DamName4</Dam>
      <Sire id="sire4">SireName4</Sire>
      <Trainer id="tr4">TrainerName4</Trainer>
    </Dog>
  </Race>
</Meet>
"""

BASIC_FORMAT_SINGLE_RACE_XML = b"""<?xml version="1.0"?>
<Meet>
  <Track>300</Track>
  <Date>01-Jan-2021</Date>
  <Quali>Y</Quali>
  <Race id="r1">
    <TipsComments><Bet>BetA</Bet><Tips>TipA</Tips></TipsComments>
    <Dog id="d1">
      <BestTime>29.50</BestTime>
      <Dam id="dam1">DamName</Dam>
      <Sire id="sire1">SireName</Sire>
      <Trainer id="tr1">TrainerName</Trainer>
    </Dog>
    <Dog id="d2">
      <BestTime>30.00</BestTime>
      <Dam id="dam2">DamName2</Dam>
      <Sire id="sire2">SireName2</Sire>
      <Trainer id="tr2">TrainerName2</Trainer>
    </Dog>
  </Race>
</Meet>
"""


# ---------------------------------------------------------------------------
# xmldict()
# ---------------------------------------------------------------------------

class TestXmldict:
    @patch('fasttrack.urllib.request.urlopen')
    def test_parses_valid_xml(self, mock_urlopen):
        xml = b"<root><item>value</item></root>"
        mock_urlopen.return_value = _make_urlopen_response(xml)

        result = xmldict("http://example.com/data.xml")

        assert result == {'root': {'item': 'value'}}

    @patch('fasttrack.urllib.request.urlopen')
    def test_raises_on_network_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        with pytest.raises(urllib.error.URLError):
            xmldict("http://example.com/data.xml")

    @patch('fasttrack.urllib.request.urlopen')
    def test_raises_on_malformed_xml(self, mock_urlopen):
        mock_urlopen.return_value = _make_urlopen_response(b"not xml <<>>")

        with pytest.raises(Exception):
            xmldict("http://example.com/data.xml")


# ---------------------------------------------------------------------------
# Fasttrack.__init__()
# ---------------------------------------------------------------------------

class TestFasttrackInit:
    @patch('fasttrack.time.sleep')
    @patch('fasttrack.xmldict')
    def test_valid_key_prints_confirmation(self, mock_xmldict, mock_sleep, capsys):
        mock_xmldict.return_value = {'meetings': None}

        ft = Fasttrack('valid-key-123')

        captured = capsys.readouterr()
        assert "Valid Security Key" in captured.out

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.xmldict')
    def test_invalid_key_prints_warning(self, mock_xmldict, mock_sleep, capsys):
        mock_xmldict.return_value = {'exception': 'Invalid Security Key'}

        ft = Fasttrack('bad-key')

        captured = capsys.readouterr()
        assert "Invalid Security Key" in captured.out

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.xmldict')
    def test_network_error_on_init_does_not_raise(self, mock_xmldict, mock_sleep, capsys):
        import urllib.error
        mock_xmldict.side_effect = urllib.error.URLError("timeout")

        # Should not raise — exception is caught and printed
        ft = Fasttrack('any-key')

        captured = capsys.readouterr()
        assert "Check you have a valid security key" in captured.out

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.xmldict')
    def test_seckey_stored_on_instance(self, mock_xmldict, mock_sleep):
        mock_xmldict.return_value = {'meetings': None}

        ft = Fasttrack('my-secret-key')

        assert ft.seckey == 'my-secret-key'

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.xmldict')
    def test_init_url_contains_seckey(self, mock_xmldict, mock_sleep):
        mock_xmldict.return_value = {'meetings': None}

        ft = Fasttrack('my-secret-key')

        called_url = mock_xmldict.call_args[0][0]
        assert 'my-secret-key' in called_url


# ---------------------------------------------------------------------------
# Fasttrack.listTracks()
# ---------------------------------------------------------------------------

class TestListTracks:
    @pytest.fixture
    def ft(self):
        with patch('fasttrack.xmldict', return_value={'meetings': None}), \
             patch('fasttrack.time.sleep'):
            return Fasttrack('test-key')

    def test_returns_dataframe(self, ft):
        result = ft.listTracks()
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, ft):
        result = ft.listTracks()
        assert set(result.columns) >= {'track_name', 'track_code', 'state'}

    def test_row_count_matches_mapping(self, ft):
        result = ft.listTracks()
        assert len(result) == len(mapping.trackCodes)

    def test_track_code_column_is_string_type(self, ft):
        result = ft.listTracks()
        assert pd.api.types.is_string_dtype(result['track_code'])

    def test_sorted_by_state_then_name(self, ft):
        result = ft.listTracks()
        expected = result.sort_values(['state', 'track_name']).reset_index(drop=True)
        pd.testing.assert_frame_equal(result, expected)


# ---------------------------------------------------------------------------
# Fasttrack.getMeetingDetail()
# ---------------------------------------------------------------------------

class TestGetMeetingDetail:
    @pytest.fixture
    def ft(self):
        with patch('fasttrack.xmldict', return_value={'meetings': None}), \
             patch('fasttrack.time.sleep'):
            return Fasttrack('test-key')

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_no_dt_end_uses_single_date(self, mock_tqdm, mock_sleep, ft):
        single_meeting = {
            'meetings': {
                'meeting': {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'}
            }
        }
        with patch('fasttrack.xmldict', return_value=single_meeting) as mock_xmldict:
            result = ft.getMeetingDetail('2021-01-01')

        assert mock_xmldict.call_count == 1
        assert isinstance(result, pd.DataFrame)

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_date_range_calls_api_for_each_day(self, mock_tqdm, mock_sleep, ft):
        single_meeting = {
            'meetings': {
                'meeting': {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'}
            }
        }
        with patch('fasttrack.xmldict', return_value=single_meeting) as mock_xmldict:
            result = ft.getMeetingDetail('2021-01-01', '2021-01-03')

        assert mock_xmldict.call_count == 3

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_invalid_date_response_returns_empty_dataframe(self, mock_tqdm, mock_sleep, ft):
        with patch('fasttrack.xmldict', return_value={'exception': 'Invalid Date Specified'}):
            result = ft.getMeetingDetail('2021-01-01')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_null_meetings_skipped(self, mock_tqdm, mock_sleep, ft):
        """Days where the API returns meetings=None should not raise or add rows."""
        with patch('fasttrack.xmldict', return_value={'meetings': None}):
            result = ft.getMeetingDetail('2021-01-01')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_single_meeting_dict_appended(self, mock_tqdm, mock_sleep, ft):
        """When meeting is a dict (not a list), it should still be included."""
        single_meeting = {
            'meetings': {
                'meeting': {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'}
            }
        }
        with patch('fasttrack.xmldict', return_value=single_meeting):
            result = ft.getMeetingDetail('2021-01-01')

        assert len(result) == 1
        assert result.iloc[0]['track'] == '300'

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_multiple_meetings_list_all_appended(self, mock_tqdm, mock_sleep, ft):
        """When meeting is a list, all entries should appear in the result."""
        multi_meeting = {
            'meetings': {
                'meeting': [
                    {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
                    {'track': '301', 'timeslot': 'Day', 'date': '01-Jan-2021'},
                ]
            }
        }
        with patch('fasttrack.xmldict', return_value=multi_meeting):
            result = ft.getMeetingDetail('2021-01-01')

        assert len(result) == 2

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, **kw: x)
    def test_track_filter_applied(self, mock_tqdm, mock_sleep, ft):
        multi_meeting = {
            'meetings': {
                'meeting': [
                    {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
                    {'track': '400', 'timeslot': 'Day', 'date': '01-Jan-2021'},
                ]
            }
        }
        with patch('fasttrack.xmldict', return_value=multi_meeting):
            result = ft.getMeetingDetail('2021-01-01', tracks=['300'])

        assert len(result) == 1
        assert result.iloc[0]['track'] == '300'

    def test_known_bug_retry_uses_undefined_variables(self, ft):
        """
        REGRESSION: Line 101 of fasttrack.py references undefined `baseUrl` and
        `seckey` instead of `self.url` and `self.seckey`. This test documents the
        bug: a NameError is raised when the retry path is hit.

        Fix: replace `baseUrl + seckey` with `self.url + self.seckey`.
        """
        import urllib.error

        call_count = 0

        def xmldict_fail_first(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise urllib.error.URLError("transient error")
            return {'meetings': None}

        with patch('fasttrack.xmldict', side_effect=xmldict_fail_first), \
             patch('fasttrack.time.sleep'), \
             patch('fasttrack.tqdm', side_effect=lambda x, **kw: x):
            with pytest.raises(NameError):
                ft.getMeetingDetail('2021-01-01')


# ---------------------------------------------------------------------------
# Fasttrack.getRaceResults()
# ---------------------------------------------------------------------------

class TestGetRaceResults:
    @pytest.fixture
    def ft(self):
        with patch('fasttrack.xmldict', return_value={'meetings': None}), \
             patch('fasttrack.time.sleep'):
            return Fasttrack('test-key')

    def _meeting_df(self):
        return pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'}
        ])

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_abandoned_meet_file_not_found_skipped(self, mock_tqdm, mock_sleep, ft):
        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value={'exception': 'File Not Found'}):
            races_df, dogs_df = ft.getRaceResults('2021-01-01', '2021-01-01')

        assert len(races_df) == 0
        assert len(dogs_df) == 0

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_returns_two_dataframes(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        race_data = xmltodict.parse(RACE_RESULTS_XML)

        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value=race_data):
            result = ft.getRaceResults('2021-01-01', '2021-01-01')

        assert isinstance(result, tuple) and len(result) == 2
        races_df, dogs_df = result
        assert isinstance(races_df, pd.DataFrame)
        assert isinstance(dogs_df, pd.DataFrame)

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_dog_with_empty_id_excluded(self, mock_tqdm, mock_sleep, ft):
        """Dogs with @id == "" should not appear in the dog results DataFrame."""
        import xmltodict
        race_data = xmltodict.parse(RACE_RESULTS_XML)

        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value=race_data):
            _, dogs_df = ft.getRaceResults('2021-01-01', '2021-01-01')

        # Only dog1 has a non-empty @id; the vacant box dog should be excluded
        assert all(dogs_df['@id'] != '')

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_trainer_fields_extracted_from_nested_dict(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        race_data = xmltodict.parse(RACE_RESULTS_XML)

        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value=race_data):
            _, dogs_df = ft.getRaceResults('2021-01-01', '2021-01-01')

        assert 'TrainerId' in dogs_df.columns
        assert 'TrainerName' in dogs_df.columns
        assert 'Trainer' not in dogs_df.columns

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_excluded_race_keys_removed(self, mock_tqdm, mock_sleep, ft):
        """Dog, Dividends, Exotics, Times should be stripped from race rows."""
        import xmltodict
        race_data = xmltodict.parse(RACE_RESULTS_XML)

        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value=race_data):
            races_df, _ = ft.getRaceResults('2021-01-01', '2021-01-01')

        for col in ['Dog', 'Dividends', 'Exotics', 'Times']:
            assert col not in races_df.columns, f"'{col}' should be stripped from race rows"

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_single_race_dict_processed(self, mock_tqdm, mock_sleep, ft):
        """When Meet.Race is a dict (single race), it should still be processed."""
        single_race_xml = b"""<?xml version="1.0"?>
<Meet>
  <Track>300</Track>
  <Date>01-Jan-2021</Date>
  <Race id="1">
    <Dog id="d1">
      <BestTime>29.50</BestTime>
      <Trainer id="t1">Trainer One</Trainer>
    </Dog>
    <Dog id="d2">
      <BestTime>30.00</BestTime>
      <Trainer id="t2">Trainer Two</Trainer>
    </Dog>
    <Dividends/>
    <Times/>
  </Race>
</Meet>
"""
        import xmltodict
        race_data = xmltodict.parse(single_race_xml)

        with patch.object(ft, 'getMeetingDetail', return_value=self._meeting_df()), \
             patch('fasttrack.xmldict', return_value=race_data):
            races_df, dogs_df = ft.getRaceResults('2021-01-01', '2021-01-01')

        assert len(races_df) == 1
        assert len(dogs_df) == 2  # both dogs in the single race


# ---------------------------------------------------------------------------
# Fasttrack.getBasicFormat() and getFullFormat()
# ---------------------------------------------------------------------------

class TestGetBasicFormat:
    @pytest.fixture
    def ft(self):
        with patch('fasttrack.xmldict', return_value={'meetings': None}), \
             patch('fasttrack.time.sleep'):
            return Fasttrack('test-key')

    @patch('fasttrack.time.sleep')
    def test_empty_meeting_returns_none_none(self, mock_sleep, ft):
        with patch.object(ft, 'getMeetingDetail', return_value=pd.DataFrame()):
            result = ft.getBasicFormat('2021-01-01')

        assert result == (None, None)

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_vacant_box_dogs_excluded(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_MULTI_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data):
            _, dogs_df = ft.getBasicFormat('2021-01-01')

        vacant_sentinels = {"* * * VACANT BOX * * *", "* * * NO RESERVE * * *"}
        assert not any(dogs_df['BestTime'].isin(vacant_sentinels))

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_dam_sire_trainer_fields_flattened(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_MULTI_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data):
            _, dogs_df = ft.getBasicFormat('2021-01-01')

        for col in ['DamId', 'DamName', 'SireId', 'SireName', 'TrainerId', 'TrainerName']:
            assert col in dogs_df.columns, f"Expected column '{col}' not found"
        for col in ['Dam', 'Sire', 'Trainer']:
            assert col not in dogs_df.columns, f"Nested column '{col}' should be removed"

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_tips_comments_unpacked(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_MULTI_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data):
            races_df, _ = ft.getBasicFormat('2021-01-01')

        assert 'TipsComments_Bet' in races_df.columns
        assert 'TipsComments_Tips' in races_df.columns
        assert 'TipsComments' not in races_df.columns

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_single_race_dict_processed(self, mock_tqdm, mock_sleep, ft):
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_SINGLE_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data):
            races_df, dogs_df = ft.getBasicFormat('2021-01-01')

        assert len(races_df) == 1
        assert len(dogs_df) == 2  # BASIC_FORMAT_SINGLE_RACE_XML has 2 dogs

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_file_not_found_skipped(self, mock_tqdm, mock_sleep, ft):
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value={'exception': 'File Not Found'}):
            races_df, dogs_df = ft.getBasicFormat('2021-01-01')

        assert len(races_df) == 0
        assert len(dogs_df) == 0


class TestGetFullFormat:
    @pytest.fixture
    def ft(self):
        with patch('fasttrack.xmldict', return_value={'meetings': None}), \
             patch('fasttrack.time.sleep'):
            return Fasttrack('test-key')

    @patch('fasttrack.time.sleep')
    def test_empty_meeting_returns_none_none(self, mock_sleep, ft):
        with patch.object(ft, 'getMeetingDetail', return_value=pd.DataFrame()):
            result = ft.getFullFormat('2021-01-01')

        assert result == (None, None)

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_uses_full_plus_url(self, mock_tqdm, mock_sleep, ft):
        """getFullFormat must use the FullPlus endpoint, not BasicPlus."""
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_SINGLE_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data) as mock_xmldict:
            ft.getFullFormat('2021-01-01')

        called_url = mock_xmldict.call_args[0][0]
        assert 'FullPlus' in called_url
        assert 'BasicPlus' not in called_url

    @patch('fasttrack.time.sleep')
    @patch('fasttrack.tqdm', side_effect=lambda x, total, **kw: x)
    def test_basic_format_uses_basic_plus_url(self, mock_tqdm, mock_sleep, ft):
        """getBasicFormat must use the BasicPlus endpoint."""
        import xmltodict
        lineup_data = xmltodict.parse(BASIC_FORMAT_SINGLE_RACE_XML)
        meeting_df = pd.DataFrame([
            {'track': '300', 'timeslot': 'Night', 'date': '01-Jan-2021'},
        ])

        with patch.object(ft, 'getMeetingDetail', return_value=meeting_df), \
             patch('fasttrack.xmldict', return_value=lineup_data) as mock_xmldict:
            ft.getBasicFormat('2021-01-01')

        called_url = mock_xmldict.call_args[0][0]
        assert 'BasicPlus' in called_url
        assert 'FullPlus' not in called_url
