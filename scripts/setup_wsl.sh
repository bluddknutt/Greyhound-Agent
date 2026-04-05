#!/usr/bin/env bash
# =============================================================================
# setup_wsl.sh — One-shot setup for Greyhound Agent on WSL (Ubuntu)
#
# Run this once on a fresh WSL Ubuntu install:
#   bash setup_wsl.sh
#
# What it does:
#   1. Installs system packages: python3, pip, git, sqlite3, jq
#   2. Clones the repo to ~/greyhound-agent/  (skipped if already present)
#   3. Creates a Python venv and installs requirements.txt
#   4. Copies .env.example → .env and prompts for API keys
#   5. Initialises the SQLite database
#   6. Runs the pytest test suite to verify the setup
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "${RED}✘${NC}  $*" >&2; exit 1; }

REPO_URL="https://github.com/bluddknutt/greyhound-agent.git"
REPO_DIR="${REPO_DIR:-$HOME/greyhound-agent}"

echo ""
echo "════════════════════════════════════════════════════"
echo "  Greyhound Agent — WSL Setup"
echo "════════════════════════════════════════════════════"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "→ Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git sqlite3 jq curl
ok "System packages installed."

# ── 2. Clone repo ─────────────────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
    warn "Repo already exists at $REPO_DIR — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only
else
    echo "→ Cloning repo to $REPO_DIR..."
    git clone "$REPO_URL" "$REPO_DIR"
    ok "Repo cloned."
fi

cd "$REPO_DIR"

# ── 3. Python venv ────────────────────────────────────────────────────────────
echo "→ Creating Python virtual environment..."
python3 -m venv venv
# shellcheck source=/dev/null
source venv/bin/activate
pip install --quiet --upgrade pip
echo "→ Installing Python dependencies..."
pip install --quiet -r requirements.txt
ok "Python venv ready at $REPO_DIR/venv"

# ── 4. .env setup ─────────────────────────────────────────────────────────────
if [ -f .env ]; then
    warn ".env already exists — skipping API key prompts. Edit $REPO_DIR/.env manually if needed."
else
    echo ""
    echo "→ Setting up environment variables (.env)..."
    cp .env.example .env

    # FAST_TRACK_API_KEY
    echo ""
    echo "  FastTrack GRV API key — register at https://fasttrack.grv.org.au"
    read -rp "  Enter FAST_TRACK_API_KEY (leave blank to skip): " ft_key
    if [ -n "$ft_key" ]; then
        sed -i "s|your_fasttrack_key_here|${ft_key}|g" .env
        ok "FAST_TRACK_API_KEY saved."
    else
        warn "FAST_TRACK_API_KEY left as placeholder."
    fi

    # ANTHROPIC_API_KEY
    echo ""
    echo "  Anthropic API key — get yours at https://console.anthropic.com/"
    read -rp "  Enter ANTHROPIC_API_KEY (leave blank to skip): " anthropic_key
    if [ -n "$anthropic_key" ]; then
        sed -i "s|your_anthropic_key_here|${anthropic_key}|g" .env
        ok "ANTHROPIC_API_KEY saved."
    else
        warn "ANTHROPIC_API_KEY left as placeholder."
    fi

    # TAB_API_KEY
    echo ""
    echo "  TAB API key — optional, leave blank if you don't have one"
    read -rp "  Enter TAB_API_KEY (leave blank to skip): " tab_key
    if [ -n "$tab_key" ]; then
        sed -i "s|your_tab_api_key_here|${tab_key}|g" .env
        ok "TAB_API_KEY saved."
    else
        warn "TAB_API_KEY left as placeholder."
    fi

    ok ".env created at $REPO_DIR/.env"
fi

# ── 5. Init SQLite DB ─────────────────────────────────────────────────────────
echo ""
echo "→ Initialising SQLite database..."
mkdir -p data logs
python3 scripts/init_db.py
ok "SQLite database ready at $REPO_DIR/data/greyhound.db"

# ── 6. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "→ Running test suite..."
if python3 -m pytest tests/ -v --tb=short -q 2>&1 | tee /tmp/greyhound_test_output.log; then
    ok "All tests passed."
else
    warn "Some tests failed — check /tmp/greyhound_test_output.log"
    echo "  (Setup is still usable; tests may require API keys or PDFs to pass fully.)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo -e "${GREEN}✔  Setup complete!${NC}"
echo ""
echo "  Repo    : $REPO_DIR"
echo "  Venv    : $REPO_DIR/venv"
echo "  Database: $REPO_DIR/data/greyhound.db"
echo "  Logs    : $REPO_DIR/logs/"
echo ""
echo "  Next steps:"
echo "    # Install cron jobs (run once):"
echo "    bash $REPO_DIR/scripts/install_cron.sh"
echo ""
echo "    # Test the daily pipeline manually:"
echo "    bash $REPO_DIR/scripts/run_daily.sh"
echo ""
echo "    # Test the results/P&L script manually:"
echo "    bash $REPO_DIR/scripts/update_results.sh"
echo "════════════════════════════════════════════════════"
