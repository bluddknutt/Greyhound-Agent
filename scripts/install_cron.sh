#!/usr/bin/env bash
# =============================================================================
# install_cron.sh — Install crontab entries for the Greyhound Agent pipeline
#
# Schedule (AEST via CRON_TZ, safe regardless of WSL system timezone):
#   07:00 AEST  — run_daily.sh     (morning picks + data fetch)
#   22:00 AEST  — update_results.sh (evening results + P&L)
#
# Idempotent: re-running this script replaces only the greyhound entries.
#
# Usage:
#   bash scripts/install_cron.sh
#   bash scripts/install_cron.sh --remove    # remove greyhound entries
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }

# ── Parse arguments ───────────────────────────────────────────────────────────
REMOVE=false
for arg in "$@"; do
    [ "$arg" = "--remove" ] && REMOVE=true
done

# ── Validate prerequisites ────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/venv/bin/activate" ]; then
    echo "ERROR: venv not found at $REPO_DIR/venv"
    echo "       Run scripts/setup_wsl.sh first."
    exit 1
fi

if [ ! -f "$REPO_DIR/scripts/run_daily.sh" ] || \
   [ ! -f "$REPO_DIR/scripts/update_results.sh" ]; then
    echo "ERROR: pipeline scripts not found in $REPO_DIR/scripts/"
    exit 1
fi

mkdir -p "$LOG_DIR"

# ── Remove existing greyhound entries ─────────────────────────────────────────
TMPFILE="$(mktemp)"
crontab -l 2>/dev/null | grep -v '# greyhound-agent' \
                       | grep -v 'run_daily.sh' \
                       | grep -v 'update_results.sh' \
                       | grep -v 'CRON_TZ=Australia/Sydney' \
                       > "$TMPFILE" || true

if [ "$REMOVE" = true ]; then
    crontab "$TMPFILE"
    rm -f "$TMPFILE"
    ok "Greyhound Agent cron entries removed."
    echo "Current crontab:"
    crontab -l 2>/dev/null || echo "  (empty)"
    exit 0
fi

# ── Build new cron entries ────────────────────────────────────────────────────
# Using CRON_TZ so that cron uses AEST regardless of the WSL system timezone.
# WSL2 often inherits UTC from the Windows host — CRON_TZ overrides this
# per-entry so no system-wide timezone change is required.

cat >> "$TMPFILE" << EOF

# greyhound-agent — auto-installed by scripts/install_cron.sh
# Edit times here or re-run install_cron.sh to update.
CRON_TZ=Australia/Sydney
# 7:00 AM AEST — morning pipeline (fetch races + generate picks)
0 7 * * * cd ${REPO_DIR} && bash scripts/run_daily.sh >> ${LOG_DIR}/cron.log 2>&1
# 10:00 PM AEST — evening results (fetch outcomes + P&L summary)
0 22 * * * cd ${REPO_DIR} && bash scripts/update_results.sh >> ${LOG_DIR}/cron.log 2>&1
EOF

# ── Install ───────────────────────────────────────────────────────────────────
crontab "$TMPFILE"
rm -f "$TMPFILE"

ok "Crontab installed."
echo ""
echo "  Schedule (CRON_TZ=Australia/Sydney):"
echo "    07:00 AEST  →  run_daily.sh"
echo "    22:00 AEST  →  update_results.sh"
echo ""
echo "  Cron output → $LOG_DIR/cron.log"
echo ""
echo "Current crontab:"
crontab -l

echo ""
warn "WSL note: WSL2 does not run cron automatically."
echo "  To enable cron in WSL, either:"
echo "    Option A — start cron at WSL login (add to ~/.bashrc or ~/.profile):"
echo "      sudo service cron start"
echo ""
echo "    Option B — use Windows Task Scheduler to launch WSL and start cron:"
echo "      wsl.exe -d Ubuntu sudo service cron start"
echo ""
echo "    Option C — use a Windows Startup Task to keep WSL cron always running."
echo "  See scripts/README.md for detailed instructions."
