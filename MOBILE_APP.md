# Greyhound Mobile App

This repo now includes a separate installable mobile-first app entrypoint.

## What it adds
- `mobile_app.py` — dedicated Flask app for phones
- `mobile_web/templates/index.html` — simplified mobile UI
- `mobile_web/static/app.js` — local state, history loading, install prompt, tab handling
- `mobile_web/static/app.css` — phone-first styling
- `mobile_web/static/manifest.webmanifest` — installable PWA manifest
- `mobile_web/static/service-worker.js` — basic shell caching for app-like behaviour
- `tests/test_mobile_app.py` — tests for the new entrypoint

## Run locally
```bash
export FLASK_APP=mobile_app
flask run --host 0.0.0.0 --port 5000
```

Or:
```bash
python mobile_app.py
```

Open from your phone on the same network:
- `http://<your-computer-lan-ip>:5000`

## Install on phone
- Open the site in Chrome or Safari
- Use the browser install/add-to-home-screen option
- On supported browsers the in-app `Install` button will appear

## Deploy
Use this start command on Render or Railway:
```bash
gunicorn mobile_app:app --bind 0.0.0.0:$PORT
```

## Notes
- TAB source can still fail outside Australian IP ranges
- Scrape source still depends on thedogs.com.au
- This adds a new app entrypoint without changing the existing `webapp/` flow
