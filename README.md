# Greyhound-Agent

Mobile-first private betting assistant built around the existing TAB pipeline.

## Repo Audit (current active entry points)

### Active now
- `run_tab_pipeline.py` — **primary** multi-source prediction pipeline (`csv`, `tab`, `scrape`).
- `webapp/app.py` — Flask API + mobile web UI wrapper for the pipeline.
- `main.py` — legacy PDF parser/scorer flow (kept for compatibility).
- `dashboard/app.py` — older read-only dashboard for `outputs/picks_{date}.csv`.

### Notes from audit
- Existing TAB logic already handled feature engineering (74 features), venue-model inference + fallback, and bet selection.
- README was outdated and described only the old PDF flow.
- Pipeline was CLI-only, with no structured API/service layer.
- No persistent run history existed for app workflows.

---

## What changed

### 1) Pipeline stabilized + wrapped (without changing methodology)
- Added `src/tab_pipeline_service.py` with reusable service functions:
  - `run_pipeline(PipelineOptions)`
  - model loading
  - fallback scoring
  - structured run payloads
- Kept `run_tab_pipeline.py` as CLI entry point.
- Preserved existing model logic and bet selection; only refactored orchestration.

### 2) Flask backend API added
`webapp/app.py` now provides:
- `GET /health`
- `POST /run`
- `GET /results/latest`
- `GET /results/history`
- `GET /races/<date>`
- `GET /` (mobile web UI)

`POST /run` request body:
```json
{
  "source": "csv|tab|scrape",
  "date": "YYYY-MM-DD",
  "venue": "optional",
  "csv_dir": "optional",
  "dry_run": false
}
```

### 3) Mobile-first frontend added
- New UI in `webapp/templates/index.html` + `webapp/static/app.css`.
- Includes:
  - source selector
  - date picker
  - venue filter
  - run button
  - results tab
  - selected bets tab
  - history tab
- Explicit warning that TAB source can be AU-IP-restricted.

### 4) Result tracking added
- Added SQLite store `src/results_store.py`.
- Persists:
  - each run payload/status
  - selected bets (stake/odds/overlay/outcome fields)
- Exposes performance summary:
  - total bets
  - strike rate
  - ROI
  - profit/loss

### 5) Testing
- Added backend route tests: `tests/test_web_app.py`.

---

## Local run instructions (exact)

### 1) Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run CLI pipeline (unchanged)
```bash
python run_tab_pipeline.py --source csv --csv-dir ./race_data/ --date 2026-04-13
```

### 3) Run web app
```bash
export FLASK_APP=webapp.app
flask run --host 0.0.0.0 --port 5000
```
Open from phone on same network:
- `http://<your-computer-lan-ip>:5000`

### 4) API quick checks
```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/results/latest
curl -X POST http://127.0.0.1:5000/run -H 'Content-Type: application/json' -d '{"source":"csv","date":"2026-04-13","csv_dir":"./race_data/"}'
```

---

## Deployment path

### Option A: Render (recommended simple path)
1. Push repo to GitHub.
2. Create **Web Service** on Render.
3. Build command:
   ```bash
   pip install -r requirements.txt
   ```
4. Start command:
   ```bash
   gunicorn webapp.app:app --bind 0.0.0.0:$PORT
   ```
5. Add environment variables from `.env.example` as needed.
6. Deploy.

### Option B: Railway
1. New project from GitHub repo.
2. Set start command:
   ```bash
   gunicorn webapp.app:app --bind 0.0.0.0:$PORT
   ```
3. Add env vars.
4. Deploy.

### Option C: Replit
1. Import GitHub repo.
2. Install deps.
3. Run:
   ```bash
   python -m flask --app webapp.app run --host 0.0.0.0 --port 5000
   ```

---

## Important assumptions / constraints
- `tab` source may fail outside Australian IP ranges (TAB access limits).
- `scrape` source depends on thedogs.com.au availability/layout stability.
- Outcome settlement is schema-ready (`bets.outcome`, `return_amount`) but still requires result ingestion wiring from `scripts/fetch_results.py` if full auto-settlement is desired.
- Existing legacy flows (`main.py`, `dashboard/app.py`) are preserved.

---

## Project structure (updated)

```text
Greyhound-Agent/
├── run_tab_pipeline.py            # CLI runner (kept)
├── webapp/
│   ├── app.py                     # Flask API + web UI server
│   ├── templates/index.html       # Mobile-first frontend
│   └── static/app.css             # Styles
├── src/
│   ├── tab_pipeline_service.py    # Pipeline service wrapper
│   ├── results_store.py           # SQLite run/bet persistence
│   ├── tab_feature_engineer.py    # 74-feature engineering
│   ├── bet_selector.py            # Value bet selection
│   └── ...
├── tests/
│   ├── test_tab_pipeline.py
│   └── test_web_app.py            # New API tests
└── .env.example
```
