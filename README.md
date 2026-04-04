# Greyhound Analytics Pipeline

Automated parsing and scoring of greyhound racing forms.

## Features
- PDF-to-text ingestion
- Race form parsing
- Trainer matching
- Feature scoring
- Top pick selection

## Usage
1. Place your `.txt` form file in the `data/` folder.
2. Run `main.py`
3. Check results in `outputs/`

## Output Files
- `todays_form.csv`: Parsed race data
- `ranked.csv`: Scored dogs
- `picks.csv`: Top 5 betting picks

## Project Structure

This repo consolidates three previously separate projects:
- **greyhound-modelling** — FastTrack GRV API client + comprehensive test suite
- **predictive-models** — thedogs.com.au scrapers + 8-component prediction engine

```
Greyhound-Agent/
├── main.py                          # PDF pipeline entry point
├── run_daily.py                     # Scheduler wrapper
├── requirements.txt                 # All dependencies
├── data/                            # PDF race form inputs
├── outputs/                         # CSV/Excel outputs
├── src/
│   ├── config.py                    # Scoring weights and thresholds
│   ├── parser.py                    # PDF form parser (regex-based)
│   ├── extract.py                   # PDF text extraction (pdfplumber)
│   ├── features.py                  # Feature engineering for PDF pipeline
│   ├── scorer.py                    # 8-component prediction engine (scraper pipeline)
│   ├── exporter.py                  # Excel export
│   ├── utils.py                     # Utilities (dir setup, file finding)
│   ├── diagnostic.py                # PDF structure diagnostics
│   ├── data/
│   │   ├── fasttrack.py             # FastTrack GRV API client (XML)
│   │   ├── fasttrack_dataset.py     # Monthly batch loader with CSV cache
│   │   └── mapping.py               # Australian + NZ track codes lookup
│   └── scrapers/
│       ├── scrape_form_guide.py     # Scrape thedogs.com.au form guide
│       └── scrape_detailed_form.py  # Scrape per-runner detailed form + box history
└── tests/
    ├── conftest.py                  # sys.path setup for test discovery
    ├── test_fasttrack.py            # FastTrack API client tests (~30 tests)
    ├── test_fasttrack_dataset.py    # Dataset loader tests (~15 tests)
    ├── test_mapping.py              # Track code data integrity tests (~12 tests)
    ├── test_parser.py               # PDF parser tests
    ├── test_exporter.py             # Excel exporter tests
    └── test_scorer.py               # Scorer pure-function tests
```

### Three Data Pipelines

| Pipeline | Input | Entry Point | Scorer |
|----------|-------|-------------|--------|
| **PDF** | Race form PDFs in `data/` | `main.py` | `src/features.py compute_features()` |
| **FastTrack API** | GRV official API (requires key in `.env`) | `src/data/fasttrack_dataset.py` | — |
| **Web scraper** | thedogs.com.au (live) | `src/scrapers/scrape_detailed_form.py` | `src/scorer.py predict()` |

### Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```
