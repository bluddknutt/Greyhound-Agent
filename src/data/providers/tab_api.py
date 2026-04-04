import requests
import json
import time
from datetime import datetime

class TabAPIProvider:
    BASE_URL = 'https://api.beta.tab.com.au/v1/tab-info-service'
    DATA_PATH = 'data/raw/tab_{date}.json'

    def __init__(self):
        self.session = requests.Session()

    def fetch_with_retries(self, method, url, *args, **kwargs):
        for attempt in range(5):  # Retry 5 times
            try:
                response = self.session.request(method, url, *args, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if 'Australian IP' in str(e):
                    print('Error: Australian IP required. Retrying...')
                else:
                    print(f'HTTP Error: {e}')
                time.sleep(2 ** attempt)  # Exponential backoff
        raise Exception('Failed to fetch data after multiple retries.')

    def fetch_meetings(self):
        url = f'{self.BASE_URL}/meetings'
        response = self.fetch_with_retries('GET', url)
        return response.json()

    def fetch_race_card(self, meeting_id):
        url = f'{self.BASE_URL}/meetings/{meeting_id}/race-card'
        response = self.fetch_with_retries('GET', url)
        return response.json()

    def fetch_runners_and_odds(self, meeting_id, race_id):
        url = f'{self.BASE_URL}/meetings/{meeting_id}/races/{race_id}/runners'
        response = self.fetch_with_retries('GET', url)
        return response.json()

    def fetch_results(self, meeting_id):
        url = f'{self.BASE_URL}/meetings/{meeting_id}/results'
        response = self.fetch_with_retries('GET', url)
        return response.json()

    def save_raw_json(self, data):
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        file_path = self.DATA_PATH.format(date=date_str)
        with open(file_path, 'w') as json_file:
            json.dump(data, json_file, indent=4)

    def scrape_tab_data(self):
        meetings = self.fetch_meetings()
        all_data = {'meetings': meetings}

        for meeting in meetings:
            meeting_id = meeting['id']
            race_card = self.fetch_race_card(meeting_id)
            all_data[meeting_id] = race_card
            for race in race_card['races']:
                race_id = race['id']
                runners_and_odds = self.fetch_runners_and_odds(meeting_id, race_id)
                all_data[meeting_id][race_id] = runners_and_odds
            results = self.fetch_results(meeting_id)
            all_data[meeting_id]['results'] = results

        self.save_raw_json(all_data)

if __name__ == '__main__':
    provider = TabAPIProvider()
    provider.scrape_tab_data()