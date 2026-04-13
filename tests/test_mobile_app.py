from mobile_app import app


def test_mobile_health_route():
    client = app.test_client()
    res = client.get('/health')
    assert res.status_code == 200
    assert res.get_json()['status'] == 'ok'
    assert res.get_json()['app'] == 'greyhound-mobile'


def test_mobile_run_route_success(monkeypatch):
    client = app.test_client()

    def fake_run_pipeline(options):
        return {
            'run_date': '2026-04-13',
            'source': options.source,
            'venue_filter': options.venue,
            'dry_run': options.dry_run,
            'summary': {'races': 2, 'bets': 1, 'runners': 16, 'venues': 1, 'total_staked': 10.0},
            'predictions': [{'venue': 'HEA', 'race_number': 1, 'runners': []}],
            'selected_bets': [{'race_number': 1, 'venue': 'HEA', 'box': 1, 'dog_name': 'X', 'model_prob': 0.2, 'bet_amount': 10.0}],
        }

    monkeypatch.setattr('mobile_app.run_pipeline', fake_run_pipeline)
    monkeypatch.setattr('mobile_app.record_run', lambda *args, **kwargs: 321)
    monkeypatch.setattr('mobile_app.performance_summary', lambda: {'total_bets': 1, 'strike_rate': 1.0, 'roi': 0.2, 'profit_loss': 2.0})

    res = client.post('/api/run', json={'source': 'csv', 'dry_run': True})
    assert res.status_code == 200
    payload = res.get_json()
    assert payload['ok'] is True
    assert payload['run_id'] == 321
    assert payload['performance']['total_bets'] == 1


def test_mobile_run_detail_not_found(monkeypatch):
    client = app.test_client()
    monkeypatch.setattr('mobile_app.fetch_run_by_id', lambda run_id: None)

    res = client.get('/api/results/999')
    assert res.status_code == 404
    payload = res.get_json()
    assert payload['ok'] is False
