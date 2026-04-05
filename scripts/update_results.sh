#!/usr/bin/env bash
# =============================================================================
# update_results.sh — Evening results and P&L script
#
# Scheduled at 10:00 PM AEST via cron (see install_cron.sh).
# Can also be run manually after races have finished:
#   bash scripts/update_results.sh
#
# Pipeline steps:
#   1. Fetch today's official race results (FastTrack API + TAB API stub)
#   2. Update the SQLite results table
#   3. Compute and print the daily P&L summary
#
# All output (stdout + stderr) is appended to logs/YYYY-MM-DD.log
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
# Append to today's log (same file as run_daily.sh)
exec >> "$LOG_FILE" 2>&1

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo ""
echo "[$(ts)] ════════════════════════════════════════"
echo "[$(ts)]   GREYHOUND AGENT — RESULTS UPDATE"
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

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f .env ]; then
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' .env | grep -v '^\s*$')
    set +a
fi

# ── Fetch results and compute P&L ─────────────────────────────────────────────
echo ""
echo "[$(ts)] ── Fetching results and computing P&L..."
if python3 scripts/fetch_results.py --date "$DATE_STR"; then
    echo "[$(ts)] Results update complete."
else
    echo "[$(ts)] WARNING: fetch_results.py encountered errors. Check log above."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "[$(ts)] ════════════════════════════════════════"
echo "[$(ts)]   RESULTS UPDATE COMPLETE"
echo "[$(ts)]   Log: $LOG_FILE"
echo "[$(ts)] ════════════════════════════════════════"
echo ""

# ── Optional: query P&L from DB and echo it to terminal as well ───────────────
if command -v sqlite3 &>/dev/null && [ -f "$REPO_DIR/data/greyhound.db" ]; then
    echo "[$(ts)] P&L from database:"
    sqlite3 "$REPO_DIR/data/greyhound.db" \
        "SELECT '  Date: ' || race_date, \
                '  Picks: ' || total_picks, \
                '  Wins: ' || wins, \
                '  Places: ' || places, \
                '  P&L: $' || printf('%.2f', profit_loss) \
         FROM pnl_log WHERE race_date = '$DATE_STR';" 2>/dev/null \
        || echo "[$(ts)]   (no P&L record found for $DATE_STR)"
fi
