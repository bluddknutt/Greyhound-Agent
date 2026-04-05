#!/usr/bin/env bash
# =============================================================================
# run_daily.sh — Morning greyhound pipeline
#
# Scheduled at 7:00 AM AEST via cron (see install_cron.sh).
# Can also be run manually at any time:
#   bash scripts/run_daily.sh
#
# Pipeline steps:
#   1. Fetch today's race data (thedogs.com.au scraper + TAB API stub)
#   2. Run the prediction pipeline (main.py → outputs/picks.csv)
#   3. Log predictions to SQLite (data/greyhound.db)
#   4. Export latest_picks.json for the Vercel site
#   5. Git commit + push latest_picks.json
#
# All output (stdout + stderr) is tee'd to logs/YYYY-MM-DD.log
# =============================================================================

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATE_STR="$(date +%Y-%m-%d)"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/$DATE_STR.log"

# ── Logging setup ─────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
# Tee all output to log file AND stdout/stderr
exec > >(tee -a "$LOG_FILE") 2>&1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo ""
echo "[$(ts)] ════════════════════════════════════════"
echo "[$(ts)]   GREYHOUND AGENT — DAILY RUN"
echo "[$(ts)]   $(date '+%A %d %B %Y %H:%M %Z')"
echo "[$(ts)] ════════════════════════════════════════"

cd "$REPO_DIR"

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ ! -f venv/bin/activate ]; then
    echo "[$(ts)] ERROR: venv not found. Run scripts/setup_wsl.sh first."
    exit 1
fi
# shellcheck source=/dev/null
source venv/bin/activate
echo "[$(ts)] Python: $(python3 --version)"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f .env ]; then
    # Export key=value pairs (skip comments and blank lines)
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' .env | grep -v '^\s*$')
    set +a
fi

# ── Step 1: Fetch race data ───────────────────────────────────────────────────
echo ""
echo "[$(ts)] ── Step 1/5: Fetching race data..."
if python3 scripts/fetch_races.py --date "$DATE_STR"; then
    echo "[$(ts)] Race data fetched OK."
else
    echo "[$(ts)] WARNING: fetch_races.py failed or returned no data. Continuing..."
fi

# ── Step 2: Run prediction pipeline ──────────────────────────────────────────
echo ""
echo "[$(ts)] ── Step 2/5: Running prediction pipeline (main.py)..."
# main.py ends with input() — pipe /dev/null to avoid blocking
if echo "" | python3 main.py; then
    echo "[$(ts)] Prediction pipeline complete."
else
    echo "[$(ts)] ERROR: main.py failed. Check logs above."
    exit 1
fi

# Verify picks output exists
if [ ! -f outputs/picks.csv ]; then
    echo "[$(ts)] ERROR: outputs/picks.csv not found after pipeline run."
    exit 1
fi
PICK_COUNT="$(tail -n +2 outputs/picks.csv | wc -l)"
echo "[$(ts)] Picks generated: $PICK_COUNT rows in outputs/picks.csv"

# ── Step 3: Log predictions to SQLite ────────────────────────────────────────
echo ""
echo "[$(ts)] ── Step 3/5: Logging predictions to SQLite..."
python3 scripts/log_predictions.py --date "$DATE_STR"
echo "[$(ts)] Predictions logged OK."

# ── Step 4: Export latest_picks.json ─────────────────────────────────────────
echo ""
echo "[$(ts)] ── Step 4/5: Exporting latest_picks.json..."
python3 scripts/export_json.py --date "$DATE_STR"
echo "[$(ts)] JSON export complete."

# ── Step 5: Git push latest_picks.json ───────────────────────────────────────
echo ""
echo "[$(ts)] ── Step 5/5: Pushing latest_picks.json to repo..."
git add latest_picks.json

if git diff --cached --quiet; then
    echo "[$(ts)] latest_picks.json unchanged — nothing to commit."
else
    git commit -m "chore: update picks $DATE_STR [skip ci]"
    # Push with retry (exponential backoff: 2s, 4s, 8s, 16s)
    PUSHED=false
    for WAIT in 2 4 8 16; do
        if git push origin HEAD; then
            PUSHED=true
            echo "[$(ts)] Pushed to remote OK."
            break
        fi
        echo "[$(ts)] Push failed — retrying in ${WAIT}s..."
        sleep "$WAIT"
    done
    if [ "$PUSHED" = false ]; then
        echo "[$(ts)] WARNING: Could not push latest_picks.json. Will retry next run."
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "[$(ts)] ════════════════════════════════════════"
echo "[$(ts)]   DAILY RUN COMPLETE"
echo "[$(ts)]   Picks: $PICK_COUNT | Log: $LOG_FILE"
echo "[$(ts)] ════════════════════════════════════════"
echo ""
