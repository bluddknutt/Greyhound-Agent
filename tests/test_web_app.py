from webapp.app import app


def test_health_route():
    client = app.test_client()
    res = client.get('/health')
    assert res.status_code == 200
    assert res.get_json()['status'] == 'ok'


def test_run_route_success(monkeypatch):
    client = app.test_client()

    def fake_run_pipeline(options):
        return {
            'run_date': '2026-04-13',
            'source': options.source,
            'venue_filter': options.venue,
            'dry_run': options.dry_run,
            'summary': {'races': 1, 'bets': 1, 'runners': 8, 'venues': 1, 'total_staked': 10.0},
            'predictions': [{'venue': 'HEA', 'race_number': 1, 'runners': []}],
            'selected_bets': [{'race_number': 1, 'venue': 'HEA', 'box': 1, 'dog_name': 'X', 'model_prob': 0.2}],
        }

    monkeypatch.setattr('webapp.app.run_pipeline', fake_run_pipeline)
    monkeypatch.setattr('webapp.app.record_run', lambda *args, **kwargs: 123)

    res = client.post('/run', json={'source': 'csv', 'dry_run': True})
    assert res.status_code == 200
    payload = res.get_json()
    assert payload['ok'] is True
    assert payload['run_id'] == 123


def test_latest_results(monkeypatch):
    client = app.test_client()
    monkeypatch.setattr('webapp.app.fetch_latest_run', lambda: {'predictions': [], 'selected_bets': []})
    monkeypatch.setattr('webapp.app.performance_summary', lambda: {'total_bets': 0, 'strike_rate': 0, 'roi': 0, 'profit_loss': 0})

    res = client.get('/results/latest')
    assert res.status_code == 200
    payload = res.get_json()
    assert payload['ok'] is True
    assert 'performance' in payload
