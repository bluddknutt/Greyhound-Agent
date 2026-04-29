"""
CSV Race File Ingester — parses Expert Form CSVs from thedogs.com.au Print Hub.

Input CSV format (one file per race):
  Dog Name,Sex,PLC,BOX,WGT,DIST,DATE,TRACK,G,TIME,WIN,BON,1 SEC,MGN,W/2G,PIR,SP
  1. DOG NAME,D,3,5,31.4,300,2026-04-03,HEA,Tier 3 - Maiden,17.589,...
  "",D,8,7,31.4,300,2026-03-27,HEA,Maiden,17.356,...

Parsing rules:
  - Row with numbered name (e.g. '1. DOG NAME') = new dog + first form line
  - Rows starting with '' = continuation form lines for same dog
  - Grade parsing: 'Tier 3 - Maiden' → 'Maiden', etc.
  - Filenames: Race_{N}_-_{VENUE}_-_{DD}_{Month}_{YYYY}.csv

Public API:
  load_race_csv(filepath) → pd.DataFrame
  load_meeting_csvs(directory, venue, date) → pd.DataFrame
  validate_csv_headers(filepath) → tuple[bool, list[str]]
"""

import logging
import os
import re
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Expected CSV header columns
EXPECTED_HEADERS = [
    "Dog Name", "Sex", "PLC", "BOX", "WGT", "DIST", "DATE",
    "TRACK", "G", "TIME", "WIN", "BON", "1 SEC", "MGN",
    "W/2G", "PIR", "SP",
]

# Fuzzy mapping for common header variations
HEADER_ALIASES = {
    "1st split": "1 SEC",
    "first split": "1 SEC",
    "1st sec": "1 SEC",
    "first sec": "1 SEC",
    "first sectional": "1 SEC",
    "margin": "MGN",
    "weight": "WGT",
    "distance": "DIST",
    "grade": "G",
    "track": "TRACK",
    "date": "DATE",
    "sex": "Sex",
    "placing": "PLC",
    "box": "BOX",
    "time": "TIME",
    "winner": "WIN",
    "win": "WIN",
    "best of night": "BON",
    "bon": "BON",
    "sp": "SP",
    "starting price": "SP",
    "pir": "PIR",
    "positions in running": "PIR",
    "w/2g": "W/2G",
    "winner/2nd": "W/2G",
    "dog name": "Dog Name",
    "name": "Dog Name",
    "dog": "Dog Name",
    "wgt": "WGT",
    "mgn": "MGN",
    "plc": "PLC",
    "dist": "DIST",
    "g": "G",
}

# Numeric columns that should be coerced to float
NUMERIC_COLS = ["WGT", "DIST", "TIME", "WIN", "BON", "1 SEC", "MGN", "SP"]

# Output column mapping from CSV columns to standardised schema
OUTPUT_COLUMNS = [
    "dog_name", "dog_number", "sex", "box", "weight", "distance",
    "date", "track", "grade", "race_number", "venue",
    "time", "win_time", "bon", "first_split", "margin",
    "w2g", "pir", "sp", "run_sequence",
]


def _clean_grade(raw_grade):
    """
    Parse grade field to extract clean grade name.

    Examples:
      'Tier 3 - Maiden'       → 'Maiden'
      'Bottom Up - Grade 7'   → 'Grade 7'
      'Rank Limit - Restricted Win' → 'Restricted Win'
      'Mixed 6/7 Heat'        → 'Mixed 6/7'
      'Maiden'                → 'Maiden'
      'Grade 5'               → 'Grade 5'
    """
    if pd.isna(raw_grade) or not isinstance(raw_grade, str):
        return raw_grade

    g = raw_grade.strip()
    if not g:
        return np.nan

    # Strip tier/qualifier prefixes: 'Tier N - X' or 'Bottom Up - X' etc.
    if " - " in g:
        parts = g.split(" - ", 1)
        prefix = parts[0].strip().lower()
        # Common prefixes to strip
        strip_prefixes = ["tier", "bottom up", "rank limit", "top up"]
        if any(prefix.startswith(p) for p in strip_prefixes):
            g = parts[1].strip()

    # Strip trailing qualifiers like 'Heat', 'Final', 'Semi'
    for suffix in [" Heat", " Final", " Semi", " Consolation"]:
        if g.endswith(suffix):
            g = g[: -len(suffix)].strip()
            break

    return g if g else np.nan


def _parse_dog_name(raw_name):
    """
    Parse dog name, stripping the number prefix.

    '1. DOG NAME' → ('DOG NAME', 1)
    'DOG NAME'    → ('DOG NAME', None)
    ''            → (None, None)  [continuation row]
    """
    if pd.isna(raw_name):
        return None, None

    name = str(raw_name).strip().strip('"')
    if not name:
        return None, None  # continuation row

    # Match numbered prefix: '1. DOG NAME' or '10. DOG NAME'
    m = re.match(r"^(\d+)\.\s*(.+)$", name)
    if m:
        return m.group(2).strip(), int(m.group(1))

    return name, None


def _parse_filename(filepath):
    """
    Extract race_number, venue, and date from filename.

    Pattern: Race_{N}_-_{VENUE}_-_{DD}_{Month}_{YYYY}.csv
    Example: Race_1_-_HEA_-_08_April_2026.csv → (1, 'HEA', '2026-04-08')
    """
    basename = Path(filepath).stem
    m = re.match(
        r"Race_(\d+)_-_([A-Za-z_]+)_-_(\d{2})_(\w+)_(\d{4})",
        basename,
    )
    if m:
        race_num = int(m.group(1))
        venue = m.group(2).replace("_", " ").strip()
        day = m.group(3)
        month_str = m.group(4)
        year = m.group(5)
        try:
            dt = datetime.strptime(f"{day} {month_str} {year}", "%d %B %Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = None
            logger.warning("Could not parse date from filename: %s", basename)
        return race_num, venue, date_str

    logger.warning("Could not parse filename pattern: %s", basename)
    return None, None, None


def _map_headers(actual_headers):
    """
    Map actual CSV headers to expected headers using fuzzy matching.

    Returns (mapped_headers, mismatched) where mismatched is a list of
    columns that could not be mapped.
    """
    mapped = []
    mismatched = []
    expected_lower = {h.lower(): h for h in EXPECTED_HEADERS}

    for h in actual_headers:
        h_stripped = h.strip()
        h_lower = h_stripped.lower()

        # Exact match (case-insensitive)
        if h_lower in expected_lower:
            mapped.append(expected_lower[h_lower])
            continue

        # Alias match
        if h_lower in HEADER_ALIASES:
            mapped.append(HEADER_ALIASES[h_lower])
            continue

        # Fuzzy match
        close = get_close_matches(
            h_lower,
            list(expected_lower.keys()) + list(HEADER_ALIASES.keys()),
            n=1,
            cutoff=0.7,
        )
        if close:
            match = close[0]
            if match in expected_lower:
                mapped.append(expected_lower[match])
            elif match in HEADER_ALIASES:
                mapped.append(HEADER_ALIASES[match])
            else:
                mapped.append(h_stripped)
                mismatched.append(h_stripped)
        else:
            mapped.append(h_stripped)
            mismatched.append(h_stripped)

    return mapped, mismatched


def validate_csv_headers(filepath):
    """
    Validate CSV headers against expected format.

    Parameters
    ----------
    filepath : str
        Path to the CSV file.

    Returns
    -------
    tuple[bool, list[str]]
        (valid, mismatched_columns) — True if all headers match,
        list of columns that could not be mapped.
    """
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            first_line = f.readline().strip()
    except (OSError, UnicodeDecodeError) as e:
        logger.error("Cannot read file %s: %s", filepath, e)
        return False, [str(e)]

    actual = [h.strip() for h in first_line.split(",")]
    _, mismatched = _map_headers(actual)

    if mismatched:
        logger.warning(
            "Header mismatch in %s — expected: %s, got unmapped: %s",
            filepath,
            EXPECTED_HEADERS,
            mismatched,
        )
        return False, mismatched

    return True, []


def load_race_csv(filepath):
    """
    Parse a single Expert Form CSV file into a standardised DataFrame.

    Each dog has a header row (numbered name) followed by 0+ continuation
    rows (empty name field). The output has one row per form line with
    metadata (dog_name, dog_number, race_number, venue) attached.

    Parameters
    ----------
    filepath : str
        Path to a Race CSV file.

    Returns
    -------
    pd.DataFrame
        Standardised DataFrame with OUTPUT_COLUMNS.
    """
    filepath = str(filepath)

    # Read raw headers and map them
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            header_line = f.readline().strip()
    except (OSError, UnicodeDecodeError) as e:
        logger.error("Cannot read %s: %s", filepath, e)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    raw_headers = [h.strip() for h in header_line.split(",")]
    mapped_headers, mismatched = _map_headers(raw_headers)

    if mismatched:
        logger.warning(
            "Unmapped columns in %s: %s — attempting best-effort parse",
            filepath,
            mismatched,
        )

    # Read the CSV with mapped headers
    try:
        df = pd.read_csv(
            filepath,
            header=None,
            names=mapped_headers,
            skiprows=1,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except Exception as e:
        logger.error("Failed to parse CSV %s: %s", filepath, e)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    if df.empty:
        logger.warning("Empty CSV: %s", filepath)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Parse filename for race metadata
    race_number, venue, file_date = _parse_filename(filepath)

    # Group rows by dog: numbered name = new dog, empty name = continuation
    dogs = []
    current_dog_name = None
    current_dog_number = None
    current_runs = []

    for _, row in df.iterrows():
        raw_name = row.get("Dog Name", "")
        dog_name, dog_number = _parse_dog_name(raw_name)

        if dog_name is not None:
            # Save previous dog's data
            if current_dog_name is not None and current_runs:
                dogs.append(
                    (current_dog_name, current_dog_number, current_runs)
                )
            current_dog_name = dog_name
            current_dog_number = dog_number
            current_runs = [row]
        else:
            # Continuation row
            if current_dog_name is not None:
                current_runs.append(row)

    # Save last dog
    if current_dog_name is not None and current_runs:
        dogs.append((current_dog_name, current_dog_number, current_runs))

    # Build output rows
    records = []
    for dog_name, dog_number, runs in dogs:
        if not str(dog_name or "").strip() or "vacant box" in str(dog_name).lower() or "no reserve" in str(dog_name).lower():
            continue
        for seq, run in enumerate(runs, 1):
            # Coerce numeric fields
            record = {
                "dog_name": dog_name,
                "dog_number": dog_number,
                "sex": run.get("Sex", ""),
                "box": _safe_int(run.get("BOX")),
                "weight": _safe_float(run.get("WGT")),
                "distance": _safe_float(run.get("DIST")),
                "date": _parse_date(run.get("DATE", "")),
                "track": run.get("TRACK", "").strip(),
                "grade": _clean_grade(run.get("G", "")),
                "race_number": race_number,
                "venue": venue,
                "time": _safe_float(run.get("TIME")),
                "win_time": _safe_float(run.get("WIN")),
                "bon": _safe_float(run.get("BON")),
                "first_split": _safe_float(run.get("1 SEC")),
                "margin": _safe_float(run.get("MGN")),
                "w2g": run.get("W/2G", "").strip(),
                "pir": run.get("PIR", "").strip(),
                "sp": _safe_float(run.get("SP")),
                "run_sequence": seq,
            }
            records.append(record)

    if not records:
        logger.warning("No dog entries found in %s", filepath)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    logger.info(
        "Parsed %s: %d dogs, %d form lines",
        Path(filepath).name,
        len(dogs),
        len(records),
    )
    return result


def load_meeting_csvs(directory, venue=None, date=None):
    """
    Load all Race CSVs from a directory, optionally filtered by venue/date.

    Parameters
    ----------
    directory : str
        Path to directory containing Race CSV files.
    venue : str, optional
        Filter to CSVs matching this venue code (case-insensitive).
    date : str, optional
        Filter to CSVs matching this date (YYYY-MM-DD format).

    Returns
    -------
    pd.DataFrame
        Concatenated DataFrame from all matching CSV files.
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.error("Directory does not exist: %s", directory)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    csv_files = sorted(directory.glob("Race_*.csv"))
    if not csv_files:
        # Also try recursive search
        csv_files = sorted(directory.rglob("Race_*.csv"))

    if not csv_files:
        logger.warning("No Race CSV files found in %s", directory)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frames = []
    for csv_path in csv_files:
        # Apply venue/date filters based on filename
        race_num, file_venue, file_date = _parse_filename(csv_path)

        if venue and file_venue and file_venue.upper() != venue.upper():
            continue
        if date and file_date and file_date != date:
            continue

        df = load_race_csv(str(csv_path))
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning(
            "No matching CSVs after filtering (venue=%s, date=%s)",
            venue,
            date,
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    logger.info(
        "Loaded %d files → %d total rows from %s",
        len(frames),
        len(result),
        directory,
    )
    return result


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_float(val):
    """Convert to float, returning NaN on failure."""
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return np.nan
    try:
        return float(str(val).replace("$", "").replace("kg", "").strip())
    except (ValueError, TypeError):
        return np.nan


def _safe_int(val):
    """Convert to int, returning None on failure."""
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _parse_date(val):
    """Parse date string to datetime, trying multiple formats."""
    if not val or (isinstance(val, str) and val.strip() == ""):
        return pd.NaT

    val = str(val).strip()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue

    return pd.NaT
