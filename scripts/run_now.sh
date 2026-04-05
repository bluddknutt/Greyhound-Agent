#!/bin/bash
export TZ="Australia/Sydney"
DATE_STR=$(date +%Y-%m-%d)
cd "$(dirname "$0")/.."
source venv/bin/activate
echo "Fetching races for $DATE_STR..."
python scripts/fetch_races.py
CSV_PATH="outputs/form_guide_${DATE_STR}.csv"
if [ ! -f "$CSV_PATH" ]; then echo "ERROR: No data"; exit 1; fi
echo "Running predictions..."
python main.py --csv "$CSV_PATH"
echo "Fetching results..."
python scripts/fetch_results.py
echo "Dashboard:"
python -m results_tracker dashboard
