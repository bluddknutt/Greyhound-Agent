# Greyhound Agent — WSL Automation Scripts

Daily greyhound betting analytics pipeline running on WSL2 (Ubuntu on Windows 11).

---

## Prerequisites

- Windows 11 with WSL2 enabled
- Ubuntu 22.04 LTS (from the Microsoft Store)
- Git configured with your GitHub credentials
- API keys (see [API Keys](#api-keys) section below)

---

## Quick Start

### 1. One-shot setup

Open a WSL terminal and run:

```bash
bash ~/greyhound-agent/scripts/setup_wsl.sh
```

This will:
- Install `python3`, `pip`, `git`, `sqlite3`, `jq`
- Clone the repo to `~/greyhound-agent/`
- Create a Python virtual environment and install `requirements.txt`
- Prompt you for your API keys and write them to `.env`
- Initialise the SQLite database at `data/greyhound.db`
- Run the pytest test suite

### 2. Install cron jobs

```bash
bash ~/greyhound-agent/scripts/install_cron.sh
```

This installs two crontab entries using `CRON_TZ=Australia/Sydney`:

| Time (AEST) | Script | Purpose |
|-------------|--------|---------|
| 07:00 | `run_daily.sh` | Fetch races + generate + push picks |
| 22:00 | `update_results.sh` | Fetch results + compute P&L |

### 3. Enable cron in WSL

WSL2 does not start services automatically. Choose one option:

**Option A — Start cron manually each session:**
```bash
sudo service cron start
```

**Option B — Auto-start cron at WSL login** (add to `~/.bashrc`):
```bash
# Auto-start cron if not running
if ! pgrep -x cron > /dev/null; then
    sudo service cron start
fi
```
Then allow passwordless sudo for cron (run `sudo visudo` and add):
```
your_username ALL=(ALL) NOPASSWD: /usr/sbin/service cron start
```

**Option C — Windows Task Scheduler** (most reliable):
1. Open Task Scheduler → Create Basic Task
2. Trigger: "At startup"
3. Action: Start a program
   - Program: `wsl.exe`
   - Arguments: `-d Ubuntu -- sudo service cron start`

---

## Manual Runs

```bash
cd ~/greyhound-agent
source venv/bin/activate

# Run the morning pipeline now (fetches races + generates picks)
bash scripts/run_daily.sh

# Run the evening results update
bash scripts/update_results.sh

# Re-run just one step
python3 scripts/fetch_races.py
python3 main.py
python3 scripts/log_predictions.py
python3 scripts/export_json.py
python3 scripts/fetch_results.py
```

---

## Script Reference

| Script | Description |
|--------|-------------|
| `setup_wsl.sh` | One-shot setup: installs packages, clones repo, creates venv, sets up `.env`, runs tests |
| `run_daily.sh` | Morning pipeline: fetch races → predict → log → export JSON → git push |
| `update_results.sh` | Evening: fetch results → update SQLite → print P&L |
| `install_cron.sh` | Install/remove crontab entries. `--remove` flag to uninstall |
| `init_db.py` | Create SQLite schema (run automatically by setup and log scripts) |
| `fetch_races.py` | Scrape thedogs.com.au + TAB API stub → `data/form_guide_YYYY-MM-DD.csv` |
| `log_predictions.py` | Insert picks.csv rows into SQLite `predictions` table |
| `export_json.py` | Convert picks.csv → `latest_picks.json` for Vercel site |
| `fetch_results.py` | FastTrack API results + TAB API stub → SQLite + P&L summary |

---

## Directory Layout After Setup

```
~/greyhound-agent/
├── .env                      # Your API keys (never committed)
├── .env.example              # Template
├── latest_picks.json         # Updated daily, auto-pushed to repo
├── data/
│   ├── greyhound.db          # SQLite database
│   └── form_guide_YYYY-MM-DD.csv   # Daily scraped race data
├── logs/
│   ├── YYYY-MM-DD.log        # Daily log (run_daily + update_results combined)
│   └── cron.log              # Cron stderr wrapper log
├── outputs/
│   ├── picks.csv             # Top pick per race
│   ├── ranked.csv            # All dogs ranked
│   └── todays_form.csv       # All parsed race data
└── scripts/                  # This directory
```

---

## SQLite Database Schema

Database file: `data/greyhound.db`

```sql
-- Top pick per race, generated each morning
predictions (
    id, race_date, track, race_number, box, dog_name,
    final_score, bet_type,   -- 'win' | 'place' | 'watch'
    created_at
)

-- Official race outcomes, fetched each evening
results (
    id, race_date, track, race_number, box, dog_name,
    finish_position, win_time,
    created_at
)

-- Daily P&L summary
pnl_log (
    id, race_date, total_picks, wins, places,
    profit_loss,   -- net $ based on $1 flat bet model
    logged_at
)
```

**Inspect the database:**
```bash
sqlite3 data/greyhound.db
.tables
SELECT * FROM pnl_log ORDER BY race_date DESC LIMIT 7;
SELECT track, race_number, dog_name, bet_type, finish_position
FROM predictions p
LEFT JOIN results r USING (race_date, track, race_number, box)
WHERE p.race_date = date('now')
ORDER BY p.track, p.race_number;
.quit
```

---

## Logs

- **`logs/YYYY-MM-DD.log`** — Full output of both `run_daily.sh` and `update_results.sh` for that day
- **`logs/cron.log`** — Cron wrapper output (useful if a job fails to start)

```bash
# Watch today's log live
tail -f logs/$(date +%Y-%m-%d).log

# Check yesterday's P&L
grep "P&L\|Profit\|DAILY" logs/$(date -d "yesterday" +%Y-%m-%d).log
```

---

## API Keys

### FastTrack GRV API (`FAST_TRACK_API_KEY`)
Official Australian greyhound race data (schedules + results).
- Register at: https://fasttrack.grv.org.au
- Used in: `src/data/fasttrack.py`, `scripts/fetch_results.py`

### Anthropic API (`ANTHROPIC_API_KEY`)
Claude AI for agent features and prediction insights.
- Register at: https://console.anthropic.com/
- Used in: future Claude agent integration

### TAB API (`TAB_API_KEY`) — Optional
TAB race and market data. The stubs in `fetch_races.py` and `fetch_results.py`
are ready to receive real TAB API calls once you have access.
- Replace the stub sections in each file with the actual TAB API HTTP calls
- See inline comments in each script for the expected request/response structure

---

## Troubleshooting

**Cron job not running?**
```bash
# Check cron service is running
sudo service cron status

# Check cron log
tail -20 logs/cron.log

# Verify crontab entries
crontab -l
```

**Python import errors?**
```bash
# Make sure venv is active
source ~/greyhound-agent/venv/bin/activate
python3 -c "import pandas; print('OK')"
```

**SQLite locked?**
```bash
# Check for stale lock
ls -la data/greyhound.db-wal data/greyhound.db-shm 2>/dev/null
# Safe to remove if no Python process is running
rm -f data/greyhound.db-wal data/greyhound.db-shm
```

**Push fails with auth error?**
```bash
# Ensure git credentials are configured
git config --global credential.helper store
# or use SSH keys — update REPO_URL in setup_wsl.sh to the SSH URL
```

**Re-run setup without cloning again:**
```bash
REPO_DIR=~/greyhound-agent bash ~/greyhound-agent/scripts/setup_wsl.sh
```

---

## Remove Cron Jobs

```bash
bash ~/greyhound-agent/scripts/install_cron.sh --remove
```
