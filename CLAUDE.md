# CLAUDE.md — Greyhound-Agent

## What this repo is
End-to-end greyhound racing prediction pipeline: data collection → feature engineering → ML inference → bet selection → deployment.

## Repo structure
- **main.py** — CLI entry point. Currently supports PDF parser flow and CSV scorer flow. Does NOT yet have a TAB API + .pkl model flow.
- **src/scorer.py** — Hand-built 7-factor composite scorer using CSV fields (pr1_time..pr6_time, box_win_pct, track_best_time). Derives win_prob from composite score. Does NOT load .pkl models.
- **src/data/** — Data providers and scrapers. TAB API provider is a stub or may not exist on all branches.
- **models/** — Serialised .pkl models: Random Forest, Gradient Boosting, XGBoost. Trained offline — do NOT retrain.
- **results_tracker/** — P&L tracking: results_tracker.py, update_results.py, dashboard.py. 64/64 tests passing.
- **latest_picks.json** — Output consumed by Vercel site (firstothefinish.vercel.app).
- **tests/** — 110+ passing tests on consolidation branch.

## Key branches
- **main** — Stable. PDF + CSV flows only.
- **claude/consolidate-repos-V1DjV** — Consolidated from 5 repos. Has .pkl models, results tracker, merged scrapers. Most complete branch.
- **feature/tab-live-pipeline** — (target) TAB API → .pkl → bet selection. May not exist yet.

## TAB API details
- Base URL: api.beta.tab.com.au
- Auth: None (public API)
- Geo-restriction: Australian IPs only. Requests from non-AU IPs silently fail.
- Greyhound racetype param: G
- Must use browser User-Agent header or requests timeout.
- Venue identification: use mnemonic from /meetings endpoint, NOT human-readable name.

## Critical constraints
- Do NOT modify existing files unless explicitly asked. Add new files only.
- Do NOT retrain .pkl models. Use existing serialised models as-is.
- Do NOT delete or overwrite latest_picks.json without producing valid replacement output.
- Feature mismatch is the #1 risk. When loading .pkl models, inspect feature_names_in_ or equivalent to confirm expected input features before running inference.
- Windows Firewall: Python needs an outbound rule to reach TAB API on the dev machine.

## Output format
latest_picks.json must match the schema expected by the Vercel site GitHub Action rebuild. Structure:
```json
{
  "generated_at": "ISO-8601 timestamp",
  "picks": [
    {
      "race": 1,
      "venue": "Venue Name",
      "runner": "Dog Name",
      "box": 3,
      "model_prob": 0.28,
      "odds": 5.0,
      "overlay_pct": 40.0,
      "stake": 2.50
    }
  ]
}
```

## Dev environment
- OS: Windows 11 (ASUS VivoBook, x64 AMD), WSL Ubuntu available
- Python default language for everything
- Claude Code in VS Code (Node.js installed)
- PythonAnywhere (Bluddknutt) — free tier, EU IP, known outbound whitelist limits
- Preferred hosting: Hetzner VPS (~$6 USD/month) for Australian IP requirement

## Testing
- Run all tests: `pytest tests/ -v`
- Results tracker tests: `pytest tests/test_results_tracker.py -v` (64/64)

## Style
- No unnecessary abstractions. Flat, readable scripts.
- Print clear error messages on failure — never silently skip.
- Log what was attempted and what blocked execution.