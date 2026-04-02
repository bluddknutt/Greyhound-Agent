# Greyhound Repository Audit

**Date:** 2026-04-02  
**Repos audited:**
- `bluddknutt/Greyhound-Agent` — main pipeline, LLM analysis, predictions
- `bluddknutt/greyhound-modelling` — Betfair-origin modelling, pytest suite
- `bluddknutt/predictive-models` — scraping, predictions (multi-sport)
- `bluddknutt/login` — utility repo (TypeScript only, **zero Python files**)

---

## 1. File Manifests

### 1.1 Greyhound-Agent (15 files, ~709 lines)

| File | Purpose | Lines | Key Imports |
|------|---------|-------|-------------|
| `debug_parser.py` | Standalone debug tool — extracts text from most-recent PDF, prints first 100 lines, regex-matches dog entries | 64 | `os`, `re`, `pdfplumber` |
| `main.py` | Top-level pipeline entry point — scans `data/` for PDFs, parses, computes features, saves `outputs/todays_form.csv` | 75 | `pandas`, `numpy`, `pdfplumber`, `src.parser`, `src.features` |
| `run_daily.py` | Scheduler wrapper — invokes `main.py` via subprocess, verifies output CSVs exist | 21 | `subprocess`, `datetime`, `os` |
| `src/config.py` | Central config — `SCORING_WEIGHTS` dict, win/place bet thresholds | 16 | _(none)_ |
| `src/diagnostic.py` | Diagnostic utility — opens first PDF, prints raw text, scans for numbered items and form patterns | 63 | `os`, `pdfplumber`, `re` |
| `src/exporter.py` | Exports dog list to timestamped Excel file with enforced column order | 40 | `pandas`, `os` |
| `src/extract.py` | PDF text extraction — finds most-recent PDF in folder, returns raw text via `pdfplumber` | 30 | `os`, `pdfplumber` |
| `src/features.py` | Feature engineering — speed, early speed, form momentum, consistency index, distance suitability, overexposure penalty. **Several fields are hardcoded placeholders.** | 150 | `pandas`, `numpy` |
| `src/main.py` | Older alternate entry point — loads PDFs as raw text files, scores by box position only, exports to Excel | 70 | `os`, `parser`, `exporter` |
| `src/parser.py` | Core PDF text parser — regex extracts race headers and all per-dog stats into a DataFrame | 98 | `pandas`, `re` |
| `src/scorer.py` | **EMPTY FILE — 0 bytes. Stub never implemented.** | 0 | _(none)_ |
| `src/utils.py` | Utility helpers — creates `outputs/` dir, finds all PDFs in configured data dir | 31 | `os`, `config` |
| `test_parser.py` | Manual smoke test — hardcoded sample race text, calls `parse_race_form`, prints results | 17 | `src.parser`, `pandas` |
| `tests/test_exporter.py` | ⚠️ **MISLABELED** — contains only a copy of `extract_text_from_latest_pdf`. No test assertions. | 30 | `os`, `pdfplumber` |
| `tests/test_parser.py` | ⚠️ **MISLABELED** — identical copy of `extract_text_from_latest_pdf`. No test assertions. | 30 | `os`, `pdfplumber` |
| `tests/test_scorer.py` | ⚠️ **MISLABELED** — identical copy of `extract_text_from_latest_pdf`. No test assertions. | 30 | `os`, `pdfplumber` |

---

### 1.2 greyhound-modelling (8 files, ~1,584 lines)

| File | Purpose | Lines | Key Imports |
|------|---------|-------|-------------|
| `src/fasttrack.py` | Client wrapper for the FastTrack GRV Data Export API — `listTracks()`, `getRaceResults()` with rate limiting, XML parsing | 393 | `urllib`, `xmltodict`, `datetime`, `pandas`, `tqdm` |
| `src/fasttrack_dataset.py` | Dataset loader — monthly date ranges, local CSV cache, API fallback, `.env`-sourced API key | 57 | `os`, `pandas`, `dotenv`, `fasttrack` |
| `src/mapping.py` | Static lookup table — all GRV track codes → name + state; timeslot mappings | 127 | _(none)_ |
| `tests/__init__.py` | Empty package marker | 0 | _(none)_ |
| `tests/conftest.py` | Pytest config — inserts `src/` into `sys.path` | 5 | `sys`, `os` |
| `tests/test_fasttrack.py` | Comprehensive mocked test suite for `fasttrack.py` — init, listTracks, getRaceResults, retry, rate limiting | 660 | `pytest`, `unittest.mock`, `pandas`, `fasttrack` |
| `tests/test_fasttrack_dataset.py` | Tests for `fasttrack_dataset.py` — mocks file I/O, API, env vars; documents pandas 2.0 `.append()` bug | 265 | `pytest`, `pandas`, `unittest.mock`, `fasttrack_dataset` |
| `tests/test_mapping.py` | Data integrity tests — validates all track entries have required keys, unique codes, valid states | 77 | `pytest`, `mapping` |

---

### 1.3 predictive-models — greyhound files (3 files, ~1,167 lines)

| File | Purpose | Lines | Key Imports |
|------|---------|-------|-------------|
| `greyhound/scrape_form_guide.py` | Scrapes daily form guide from `thedogs.com.au` — all venues, all races, all runners → CSV | 222 | `re`, `time`, `requests`, `pandas`, `datetime` |
| `greyhound/scrape_detailed_form.py` | Scrapes detailed per-runner form — past 6 starts, box draw history, best track times, speedmap | 416 | `re`, `time`, `requests`, `pandas`, `numpy`, `datetime` |
| `greyhound/predict_races.py` | **Full prediction engine** — 8-component composite score (ELO speed, EWMA form, box bias, class rating, sectional speed, consistency, margins, track fitness); normalises to win probability; top-4 per race | 529 | `pandas`, `numpy`, `datetime` |

### 1.4 predictive-models — non-greyhound files (8 files, ~2,196 lines)

| File | Purpose | Lines | Key Imports |
|------|---------|-------|-------------|
| `afl/afl_data_cleaning_v2.py` | AFL data cleaning — normalises team names, odds/results/player stats | 133 | `pandas` |
| `afl/afl_feature_creation_v2.py` | AFL EWMA feature engineering | 245 | `pandas`, `numpy` |
| `afl/afl_modelling_v2.py` | AFL logistic regression predictor | 184 | `sklearn`, `pandas`, `numpy` |
| `epl/data_preparation_functions.py` | EPL data prep library — ELO/TrueSkill ratings, log-loss utilities | 521 | `pandas`, `sklearn`, `numpy` |
| `epl/weekly_prediction_functions.py` | EPL weekly prediction utils — Betfair market data, timezone conversion | 76 | `pandas`, `sklearn`, `pytz`, `imp` ⚠️ |
| `nrl/functions/prod_functions.py` | NRL production — TrueSkill/ELO, H2O AutoML, Betfair API, S3 | 454 | `trueskill`, `h2o`, `betfairlightweight`, `boto3` |
| `nrl/prod.py` | NRL production runner — load model, predict, place Betfair bets | 76 | `h2o`, `betfairlightweight`, `boto3` |
| `super-rugby/functions/prod_functions.py` | Super Rugby production functions — near-identical to NRL | 430 | _(identical to NRL)_ |
| `super-rugby/prod.py` | Super Rugby runner — near-identical to NRL | 77 | _(identical to NRL)_ |

### 1.5 login (0 Python files)

TypeScript/Node.js project only. Files: `src/index.ts`, `src/login.ts`, `test/index-spec.ts`, `test/login-spec.ts`, `package.json`, `tsconfig.json`. **Not relevant to migration.**

---

## 2. Duplicate / Overlapping Functionality

| Overlap | Files Involved | Notes |
|---------|---------------|-------|
| **PDF extraction function** | `src/extract.py`, `tests/test_exporter.py`, `tests/test_parser.py`, `tests/test_scorer.py` (all in Greyhound-Agent) | All four contain an identical `extract_text_from_latest_pdf()` function. The three test files are completely non-functional as tests. |
| **Feature engineering** | `Greyhound-Agent/src/features.py` vs `predictive-models/greyhound/predict_races.py` | Agent version has basic metrics with **hardcoded placeholder values**. predictive-models version has a full 8-component composite scoring system (ELO, EWMA, box bias, class rating, sectionals, consistency, margins, track fitness). |
| **Scoring/prediction** | `Greyhound-Agent/src/scorer.py` (0 bytes) vs `predictive-models/greyhound/predict_races.py` | scorer.py is an empty stub; predict_races.py is a complete implementation. |
| **Data sourcing — 3 parallel approaches** | `Greyhound-Agent/src/extract.py` (PDF), `greyhound-modelling/src/fasttrack.py` (GRV API), `predictive-models/greyhound/scrape_*.py` (web scraping) | Three completely separate data pipelines for the same domain. No integration exists between them. |
| **NRL and Super Rugby prod code** | `nrl/functions/prod_functions.py` vs `super-rugby/functions/prod_functions.py` | Near-identical scripts (~430 lines each). No shared base class or utility module — pure copy-paste duplication. |
| **Duplicate function definition** | `predictive-models/afl/afl_modelling_v2.py` lines ~14 and ~37 | `get_next_week_odds()` is defined twice; the second silently overwrites the first. |

---

## 3. Functionality in greyhound-modelling / predictive-models NOT in Greyhound-Agent

| Capability | Source File | Description |
|-----------|------------|-------------|
| **FastTrack GRV API client** | `greyhound-modelling/src/fasttrack.py` | Full XML API wrapper for official GRV data export — track listing, race results, rate limiting |
| **API dataset loader with caching** | `greyhound-modelling/src/fasttrack_dataset.py` | Monthly batch fetch with local CSV cache; `.env` API key management |
| **Track codes lookup table** | `greyhound-modelling/src/mapping.py` | All Australian + NZ greyhound track codes → name + state |
| **Web scraper — form guide** | `predictive-models/greyhound/scrape_form_guide.py` | Scrapes `thedogs.com.au` daily form guide: all venues + races today → CSV |
| **Web scraper — detailed form** | `predictive-models/greyhound/scrape_detailed_form.py` | Per-runner detail: last 6 starts, box draw history, best times, speedmap |
| **Full prediction engine** | `predictive-models/greyhound/predict_races.py` | 8-component composite probability score; win probability normalisation; top-4 per race |
| **Proper pytest test suite** | `greyhound-modelling/tests/` (4 files, ~1,007 lines) | Comprehensive mocked tests with conftest; covers API, dataset loader, mapping. Greyhound-Agent's test files contain no actual assertions. |

---

## 4. Known Bugs / Technical Debt

| Issue | File | Severity |
|-------|------|----------|
| Three test files contain copy of `extract.py` — no actual tests | `tests/test_exporter.py`, `tests/test_parser.py`, `tests/test_scorer.py` | High |
| `src/scorer.py` is empty — scoring not implemented | `Greyhound-Agent/src/scorer.py` | High |
| `src/features.py` uses hardcoded placeholder values for `BestTimeSec`, `SectionalSec`, `Last3TimesSec`, `Margins` | `Greyhound-Agent/src/features.py` | High |
| `TODAY` hardcoded as `datetime(2026, 3, 18)` | `predictive-models/greyhound/predict_races.py` | High |
| `DataFrame.append()` used — removed in pandas 2.0 | `greyhound-modelling/src/fasttrack_dataset.py` | Medium |
| `imp` module imported — removed in Python 3.12 | `predictive-models/epl/weekly_prediction_functions.py` | Medium |
| `get_next_week_odds()` defined twice | `predictive-models/afl/afl_modelling_v2.py` | Medium |
| Duplicate `import json` | `predictive-models/nrl/prod.py` | Low |
| NRL and Super Rugby prod code are near-identical (no shared base) | `nrl/`, `super-rugby/` | Low |

---

## 5. Migration Plan

> **Actions defined:**
> - **copy** — file has no equivalent in Greyhound-Agent; bring it in as-is
> - **merge** — Greyhound-Agent has a stub/inferior version; integrate logic from source
> - **replace** — Greyhound-Agent file is wrong/broken; replace it entirely
> - **skip** — non-greyhound content; out of scope

### 5.1 From greyhound-modelling

| Source File | Destination in Greyhound-Agent | Action | Notes |
|-------------|-------------------------------|--------|-------|
| `src/fasttrack.py` | `src/data/fasttrack.py` | **copy** | New data source — GRV API client; fix pandas 2.0 `.append()` bug on arrival |
| `src/fasttrack_dataset.py` | `src/data/fasttrack_dataset.py` | **copy** | Caching dataset loader; fix `DataFrame.append()` → `pd.concat()` |
| `src/mapping.py` | `src/data/mapping.py` | **copy** | Track codes lookup — needed by fasttrack and downstream features |
| `tests/__init__.py` | `tests/__init__.py` | **copy** | Restore proper package marker (currently missing) |
| `tests/conftest.py` | `tests/conftest.py` | **copy** | Adds `src/` to `sys.path`; required for test discovery |
| `tests/test_fasttrack.py` | `tests/test_fasttrack.py` | **copy** | 660-line comprehensive test suite |
| `tests/test_fasttrack_dataset.py` | `tests/test_fasttrack_dataset.py` | **copy** | Includes pandas 2.0 compatibility patch |
| `tests/test_mapping.py` | `tests/test_mapping.py` | **copy** | Data integrity tests for track codes |

### 5.2 From predictive-models/greyhound

| Source File | Destination in Greyhound-Agent | Action | Notes |
|-------------|-------------------------------|--------|-------|
| `greyhound/scrape_form_guide.py` | `src/scrapers/scrape_form_guide.py` | **copy** | New capability — live web scraping as alternative to PDF input |
| `greyhound/scrape_detailed_form.py` | `src/scrapers/scrape_detailed_form.py` | **copy** | New capability — per-runner detailed form; provides real values for the placeholder fields in `features.py` |
| `greyhound/predict_races.py` | merge into `src/scorer.py` + `src/features.py` | **merge** | Fills the empty `scorer.py`; replaces hardcoded placeholder values in `features.py` with the 8-component composite system; fix hardcoded `TODAY` → `datetime.now()` |

### 5.3 Greyhound-Agent internal fixes (no migration source needed)

| File | Action | Notes |
|------|--------|-------|
| `tests/test_exporter.py` | **replace** | Rewrite as actual exporter tests using `src/exporter.py` |
| `tests/test_parser.py` | **replace** | Rewrite as actual parser tests using `src/parser.py` |
| `tests/test_scorer.py` | **replace** | Rewrite as actual scorer tests once `src/scorer.py` is implemented |
| `src/main.py` | **merge** | Consolidate with top-level `main.py`; remove broken relative import (`from parser import ...`) |

### 5.4 From predictive-models — non-greyhound (skip)

| Source File | Action | Notes |
|-------------|--------|-------|
| `afl/afl_data_cleaning_v2.py` | **skip** | AFL-specific; out of scope |
| `afl/afl_feature_creation_v2.py` | **skip** | AFL-specific; out of scope |
| `afl/afl_modelling_v2.py` | **skip** | AFL-specific; out of scope |
| `epl/data_preparation_functions.py` | **skip** | EPL-specific; out of scope |
| `epl/weekly_prediction_functions.py` | **skip** | EPL-specific; deprecated `imp` module |
| `nrl/functions/prod_functions.py` | **skip** | NRL-specific; out of scope |
| `nrl/prod.py` | **skip** | NRL-specific; out of scope |
| `super-rugby/functions/prod_functions.py` | **skip** | Super Rugby-specific; out of scope |
| `super-rugby/prod.py` | **skip** | Super Rugby-specific; out of scope |

### 5.5 login repo

| Action | Notes |
|--------|-------|
| **skip** | TypeScript-only; zero Python files; no migration content |

---

## 6. Recommended Target Structure for Greyhound-Agent

```
Greyhound-Agent/
├── main.py                          # Keep — consolidate with src/main.py
├── run_daily.py                     # Keep
├── .env                             # Add — API key for FastTrack
├── data/                            # PDF inputs (existing)
├── outputs/                         # CSV/Excel outputs (existing)
├── src/
│   ├── config.py                    # Keep — add FastTrack/scraper config keys
│   ├── exporter.py                  # Keep
│   ├── extract.py                   # Keep — deduplicate (remove copies in tests/)
│   ├── features.py                  # Merge — replace placeholder values with real scoring components
│   ├── parser.py                    # Keep
│   ├── scorer.py                    # Merge — implement from predict_races.py
│   ├── utils.py                     # Keep
│   ├── data/
│   │   ├── fasttrack.py             # NEW — from greyhound-modelling (fix pandas 2.0)
│   │   ├── fasttrack_dataset.py     # NEW — from greyhound-modelling
│   │   └── mapping.py               # NEW — from greyhound-modelling
│   └── scrapers/
│       ├── scrape_form_guide.py     # NEW — from predictive-models
│       └── scrape_detailed_form.py  # NEW — from predictive-models
└── tests/
    ├── __init__.py                  # Replace — proper package marker
    ├── conftest.py                  # NEW — from greyhound-modelling
    ├── test_exporter.py             # Replace — write real exporter tests
    ├── test_parser.py               # Replace — write real parser tests
    ├── test_scorer.py               # Replace — write real scorer tests (after implementation)
    ├── test_fasttrack.py            # NEW — from greyhound-modelling
    ├── test_fasttrack_dataset.py    # NEW — from greyhound-modelling
    └── test_mapping.py              # NEW — from greyhound-modelling
```

---

## 7. Summary

| Metric | Value |
|--------|-------|
| Total Python files audited | 34 (across 3 repos; login has 0) |
| Total lines of Python | ~5,656 |
| Greyhound-relevant files | 26 |
| Files to **copy** into Greyhound-Agent | 10 |
| Files to **merge** into Greyhound-Agent | 3 |
| Files to **replace** (broken stubs/wrong content) | 4 |
| Files to **skip** (non-greyhound) | 9 |
| Critical bugs identified | 4 (empty scorer, hardcoded date, placeholder features, broken test files) |
