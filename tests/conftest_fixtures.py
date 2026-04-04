import pytest
import json

@pytest.fixture(scope='module')
def form_guide_fixture():
    # Load HTML fixture for thedogs.com.au form guide
    return '''<html><body><div class='form-guide'>...</div></body></html>'''

@pytest.fixture(scope='module')
def tab_api_meetings_fixture():
    # Load JSON fixture for TAB API meetings
    return json.dumps({
        "meetings": [
            {"meetingId": 1, "name": "Meeting 1", "time": "2022-01-01T12:00:00Z"},
            {"meetingId": 2, "name": "Meeting 2", "time": "2022-01-01T14:00:00Z"}
        ]
    })

@pytest.fixture(scope='module')
def runners_fixture():
    # Load JSON fixture for runners
    return json.dumps({
        "runners": [
            {"runnerId": 101, "name": "Runner 1", "form": "WWLWL"},
            {"runnerId": 102, "name": "Runner 2", "form": "LWLLW"}
        ]
    })

@pytest.fixture(scope='module')
def results_fixture():
    # Load JSON fixture for race results
    return json.dumps({
        "results": [
            {"raceId": 201, "winner": "Runner 1", "time": "29.50"},
            {"raceId": 202, "winner": "Runner 2", "time": "30.10"}
        ]
    })

# Sample usage of fixtures in tests
# def test_form_guide(form_guide_fixture):
#     assert '<div class='form-guide'>' in form_guide_fixture

# def test_tab_api_meetings(tab_api_meetings_fixture):
#     data = json.loads(tab_api_meetings_fixture)
#     assert len(data['meetings']) > 0
