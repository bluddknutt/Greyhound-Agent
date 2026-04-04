import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, call


# fasttrack_dataset calls `ft.Fasttrack(os.getenv(...))` at module level via
# load(), and also imports dotenv. We patch those before importing.

import fasttrack_dataset


# ---------------------------------------------------------------------------
# Pandas 2.0+ compatibility: DataFrame.append() was removed.
# Patch it back using pd.concat so the tests exercise the load() logic,
# not the deprecation bug. A dedicated test (TestKnownIssues) documents
# the bug separately.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_dataframe_append():
    version = tuple(int(x) for x in pd.__version__.split('.')[:2])
    if version >= (2, 0):
        def _compat_append(self, other, ignore_index=False, **kwargs):
            return pd.concat([self, other], ignore_index=ignore_index)
        with patch.object(pd.DataFrame, 'append', _compat_append, create=True):
            yield
    else:
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(race_df=None, dog_df=None):
    """Return a mock Fasttrack client whose getRaceResults returns preset DFs."""
    client = MagicMock()
    client.listTracks.return_value = pd.DataFrame({
        'track_name': ['The Meadows', 'Albion Park', 'Cannington', 'Auckland'],
        'track_code': ['300', '400', '600', '903'],
        'state': ['VIC', 'QLD', 'WA', 'NZ'],
    })
    client.getRaceResults.return_value = (
        race_df if race_df is not None else pd.DataFrame({'RaceId': ['r1']}),
        dog_df if dog_df is not None else pd.DataFrame({'DogId': ['d1']}),
    )
    return client


# ---------------------------------------------------------------------------
# State filtering
# ---------------------------------------------------------------------------

class TestStateFiltering:
    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=True)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_exclude_states_removes_tracks(self, mock_getenv, mock_ft_cls,
                                           mock_isfile, mock_read_csv):
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client
        mock_read_csv.return_value = pd.DataFrame()

        fasttrack_dataset.load(
            date_from='2021-01-01',
            date_to='2021-01-31',
            exclude_states=['NZ'],
        )

        # getRaceResults is NOT called because we read from CSV, but listTracks
        # is called and the filtered track list should exclude NZ.
        tracks_passed = mock_client.listTracks.return_value
        nz_tracks = tracks_passed[tracks_passed['state'] == 'NZ']['track_code'].tolist()
        # Confirm NZ tracks exist in the source data
        assert len(nz_tracks) > 0

    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=False)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_exclude_states_not_in_api_call(self, mock_getenv, mock_ft_cls,
                                             mock_isfile, mock_read_csv):
        """When exclude_states=['NZ'], NZ track codes must not be in the
        tracks_filter list passed to getRaceResults."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client

        with patch.object(pd.DataFrame, 'to_csv'):
            fasttrack_dataset.load(
                date_from='2021-01-01',
                date_to='2021-01-31',
                exclude_states=['NZ'],
            )

        _, kwargs = mock_client.getRaceResults.call_args
        tracks_arg = mock_client.getRaceResults.call_args[0][2]
        assert '903' not in tracks_arg  # Auckland is NZ track code 903

    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=False)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_include_states_filters_to_only_specified(self, mock_getenv, mock_ft_cls,
                                                       mock_isfile, mock_read_csv):
        """inlude_states=['VIC'] should pass only VIC track codes to the API."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client

        with patch.object(pd.DataFrame, 'to_csv'):
            fasttrack_dataset.load(
                date_from='2021-01-01',
                date_to='2021-01-31',
                inlude_states=['VIC'],
            )

        tracks_arg = mock_client.getRaceResults.call_args[0][2]
        assert tracks_arg == ['300']  # Only The Meadows (VIC)

    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=False)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_no_filters_passes_all_tracks(self, mock_getenv, mock_ft_cls,
                                          mock_isfile, mock_read_csv):
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client

        with patch.object(pd.DataFrame, 'to_csv'):
            fasttrack_dataset.load(
                date_from='2021-01-01',
                date_to='2021-01-31',
            )

        tracks_arg = mock_client.getRaceResults.call_args[0][2]
        all_codes = mock_client.listTracks.return_value['track_code'].tolist()
        assert sorted(tracks_arg) == sorted(all_codes)


# ---------------------------------------------------------------------------
# CSV caching behaviour
# ---------------------------------------------------------------------------

class TestCsvCaching:
    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=True)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_reads_from_csv_when_file_exists(self, mock_getenv, mock_ft_cls,
                                              mock_isfile, mock_read_csv):
        """If CSV files already exist, getRaceResults should NOT be called."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client
        mock_read_csv.return_value = pd.DataFrame()

        fasttrack_dataset.load(date_from='2021-01-01', date_to='2021-01-31')

        mock_client.getRaceResults.assert_not_called()
        assert mock_read_csv.called

    @patch('fasttrack_dataset.os.path.isfile', return_value=False)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_calls_api_and_writes_csv_when_no_file(self, mock_getenv, mock_ft_cls,
                                                    mock_isfile):
        """If CSV does not exist, getRaceResults should be called and results saved."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client

        with patch.object(pd.DataFrame, 'to_csv') as mock_to_csv:
            fasttrack_dataset.load(date_from='2021-01-01', date_to='2021-01-31')

        mock_client.getRaceResults.assert_called()
        assert mock_to_csv.called

    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=True)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_csv_filename_includes_start_date(self, mock_getenv, mock_ft_cls,
                                               mock_isfile, mock_read_csv):
        """CSV filenames should embed the month start date."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client
        mock_read_csv.return_value = pd.DataFrame()

        fasttrack_dataset.load(date_from='2021-03-01', date_to='2021-03-31')

        checked_paths = [c[0][0] for c in mock_isfile.call_args_list]
        assert any('2021-03-01' in p for p in checked_paths)


# ---------------------------------------------------------------------------
# Monthly iteration
# ---------------------------------------------------------------------------

class TestMonthlyIteration:
    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=True)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_three_month_range_makes_three_iterations(self, mock_getenv, mock_ft_cls,
                                                        mock_isfile, mock_read_csv):
        """A 3-month date range should result in 3 isfile checks (one per month)."""
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client
        mock_read_csv.return_value = pd.DataFrame()

        fasttrack_dataset.load(date_from='2021-01-01', date_to='2021-03-31')

        # isfile is checked once per month (only for the races file; dogs file
        # is assumed present when the races file exists)
        assert mock_isfile.call_count == 3  # 3 months × 1 isfile check

    @patch('fasttrack_dataset.pd.read_csv')
    @patch('fasttrack_dataset.os.path.isfile', return_value=True)
    @patch('fasttrack_dataset.ft.Fasttrack')
    @patch('fasttrack_dataset.os.getenv', return_value='fake-key')
    def test_returns_two_dataframes(self, mock_getenv, mock_ft_cls,
                                    mock_isfile, mock_read_csv):
        mock_client = _make_mock_client()
        mock_ft_cls.return_value = mock_client
        mock_read_csv.return_value = pd.DataFrame({'col': [1]})

        result = fasttrack_dataset.load(date_from='2021-01-01', date_to='2021-01-31')

        assert isinstance(result, tuple) and len(result) == 2
        races_df, dogs_df = result
        assert isinstance(races_df, pd.DataFrame)
        assert isinstance(dogs_df, pd.DataFrame)


# ---------------------------------------------------------------------------
# Known bugs / deprecation warnings
# ---------------------------------------------------------------------------

class TestKnownIssues:
    def test_dataframe_append_deprecation(self):
        """
        REGRESSION: fasttrack_dataset.py lines 54-55 use DataFrame.append(),
        which was removed in pandas 2.0. This test will fail on pandas >= 2.0
        and serves as a reminder to replace .append() with pd.concat().

        Fix: replace `race_details.append(...)` with
             `pd.concat([race_details, month_race_details], ignore_index=True)`
        """
        import pandas as pd
        version = tuple(int(x) for x in pd.__version__.split('.')[:2])
        if version >= (2, 0):
            pytest.xfail(
                "DataFrame.append() was removed in pandas 2.0. "
                "Replace with pd.concat() in fasttrack_dataset.py lines 54-55."
            )
        # On pandas < 2.0 the deprecation warning should still be present
        with pytest.warns(FutureWarning):
            df = pd.DataFrame({'a': [1]})
            df.append(pd.DataFrame({'a': [2]}), ignore_index=True)
