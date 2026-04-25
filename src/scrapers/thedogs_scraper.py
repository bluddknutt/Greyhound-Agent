"""
thedogs.com.au Print Hub Scraper — downloads race data files for all venues
on a given date from https://www.thedogs.com.au/racing/the-print-hub

Downloads per venue:
  - The Hound selections (PDF)
  - Expert Form CSV (primary pipeline input) + PDF
  - Racebook SHORT (PDF)
  - Racebook LONG (PDF)

Directory structure:
  downloads/{date}/{venue_slug}/
    the_hound.pdf
    expert_form.csv
    expert_form.pdf
    racebook_short.pdf
    racebook_long.pdf

CLI:
  python -m src.scrapers.thedogs_scraper
  python -m src.scrapers.thedogs_scraper --date 2026-04-11
  python -m src.scrapers.thedogs_scraper --venue ballarat
  python -m src.scrapers.thedogs_scraper --list-venues
  python -m src.scrapers.thedogs_scraper --output-dir ./race_data/

Public API:
  scrape_print_hub(date_str, output_dir, venue_filter) → dict
  list_available_venues(date_str) → list[str]
  download_file(url, dest_path) → bool
"""

import argparse
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)

PRINT_HUB_URL = "https://www.thedogs.com.au/racing/the-print-hub"
BASE_URL = "https://www.thedogs.com.au"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

AEST = timezone(timedelta(hours=10))

# Rate limit between downloads (seconds)
DOWNLOAD_RATE_LIMIT = 1.0

# File type identifiers used in the download dict
FILE_TYPES = [
    "the_hound_pdf",
    "expert_form_csv",
    "expert_form_pdf",
    "racebook_short",
    "racebook_long",
]

# File type → local filename
FILE_TYPE_NAMES = {
    "the_hound_pdf": "the_hound.pdf",
    "expert_form_csv": "expert_form.csv",
    "expert_form_pdf": "expert_form.pdf",
    "racebook_short": "racebook_short.pdf",
    "racebook_long": "racebook_long.pdf",
}


def _parse_race_csv_filename(csv_url_or_name):
    """Extract race metadata from a Race_*.csv name or URL path."""
    path = urlparse(csv_url_or_name).path
    filename = os.path.basename(path) or csv_url_or_name
    filename = unquote(filename)

    m = re.match(
        r"Race_(\d+)_-_([A-Za-z_]+)_-_(\d{2})_(\w+)_(\d{4})\.csv$",
        filename,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    race_num = int(m.group(1))
    venue = m.group(2).replace("_", " ").strip()
    day = m.group(3)
    month = m.group(4)
    year = m.group(5)

    try:
        race_date = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

    return {
        "filename": filename,
        "race_number": race_num,
        "venue": venue,
        "slug": _slugify(venue),
        "date": race_date,
    }


def _fetch_html(url):
    """Fetch HTML with retry logic."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == 2:
                logger.error("Failed to fetch %s: %s", url, e)
                return None
            time.sleep(1)
    return None


def download_file(url, dest_path):
    """
    Download a file from URL to dest_path.

    Parameters
    ----------
    url : str
        URL to download from.
    dest_path : str
        Local file path to save to.

    Returns
    -------
    bool
        True if download succeeded, False otherwise.
    """
    # Skip if file already exists
    if os.path.exists(dest_path):
        logger.info("Skipping (already exists): %s", dest_path)
        return True

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            resp.raise_for_status()

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = os.path.getsize(dest_path) / 1024
            logger.info("Downloaded %s (%.1f KB)", dest_path, size_kb)
            return True

        except requests.RequestException as e:
            if attempt == 2:
                logger.error("Failed to download %s: %s", url, e)
                return False
            time.sleep(1)

    return False


def _slugify(name):
    """Convert venue name to filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def _parse_print_hub(html, target_date_str):
    """
    Parse Print Hub HTML to extract venue info and download URLs.

    Parameters
    ----------
    html : str
        Raw HTML of the Print Hub page.
    target_date_str : str
        Date in YYYY-MM-DD format.

    Returns
    -------
    list[dict]
        List of venue dicts with keys: name, slug, downloads (dict of file_type→url).
    """
    links = re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)
    if not links:
        logger.warning("No links found on Print Hub page")
        return []

    by_venue = {}
    skipped = 0
    for raw_link in links:
        if ".csv" not in raw_link.lower() or "race_" not in raw_link.lower():
            continue

        full_url = raw_link if raw_link.startswith("http") else BASE_URL + raw_link
        meta = _parse_race_csv_filename(full_url)
        if not meta:
            skipped += 1
            continue

        if meta["date"] != target_date_str:
            continue

        venue_bucket = by_venue.setdefault(
            meta["venue"],
            {"name": meta["venue"], "slug": meta["slug"], "race_csvs": []},
        )
        venue_bucket["race_csvs"].append(
            {
                "race_number": meta["race_number"],
                "filename": meta["filename"],
                "url": full_url,
            }
        )

    venues = list(by_venue.values())
    for venue in venues:
        venue["race_csvs"].sort(key=lambda x: x["race_number"])

    logger.info(
        "Found %d venues and %d Expert Form CSV links for %s (%d non-race CSV links skipped)",
        len(venues),
        sum(len(v["race_csvs"]) for v in venues),
        target_date_str,
        skipped,
    )
    return venues


def list_available_venues(date_str):
    """
    List venues available on the Print Hub for a given date.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.

    Returns
    -------
    list[str]
        List of venue names.
    """
    html = _fetch_html(PRINT_HUB_URL)
    if not html:
        logger.error("Could not fetch Print Hub page")
        return []

    venues = _parse_print_hub(html, date_str)
    return [v["name"] for v in venues]


def scrape_print_hub(date_str, output_dir="./downloads/", venue_filter=None):
    """
    Scrape the Print Hub and download race data files.

    Parameters
    ----------
    date_str : str
        Date in YYYY-MM-DD format.
    output_dir : str
        Base directory for downloads. Files saved as:
        {output_dir}/{date_str}/{venue_slug}/{filename}
    venue_filter : str, optional
        Filter to a specific venue (case-insensitive partial match).

    Returns
    -------
    dict
        Mapping of {venue_name: {file_type: filepath}}.
    """
    html = _fetch_html(PRINT_HUB_URL)
    if not html:
        logger.error("Could not fetch Print Hub page")
        return {}

    venues = _parse_print_hub(html, date_str)
    if not venues:
        logger.error("No venues found for %s", date_str)
        return {}

    # Apply venue filter
    if venue_filter:
        filter_lower = venue_filter.lower()
        venues = [
            v for v in venues
            if filter_lower in v["name"].lower()
            or filter_lower in v["slug"]
        ]
        if not venues:
            logger.warning(
                "No venues match filter '%s'. Available: %s",
                venue_filter,
                ", ".join(v["name"] for v in _parse_print_hub(html, date_str)),
            )
            return {}

    results = {}
    for venue in venues:
        venue_dir = os.path.join(output_dir, date_str, venue["slug"])
        venue_results = {}

        logger.info("Downloading files for %s...", venue["name"])

        for race_csv in venue.get("race_csvs", []):
            filename = race_csv["filename"]
            url = race_csv["url"]
            race_number = race_csv["race_number"]
            dest = os.path.join(venue_dir, filename)

            if download_file(url, dest):
                venue_results[f"expert_form_csv_r{race_number}"] = dest
            else:
                logger.warning(
                    "Could not download expert form CSV for %s R%s",
                    venue["name"],
                    race_number,
                )

            time.sleep(DOWNLOAD_RATE_LIMIT)

        # Log what was downloaded
        n_files = len(venue_results)
        if n_files > 0:
            logger.info(
                "Downloaded %d files for %s",
                n_files,
                venue["name"],
            )
        else:
            logger.warning("No files downloaded for %s", venue["name"])

        results[venue["name"]] = venue_results

    logger.info(
        "Scraping complete: %d venues, %d total files",
        len(results),
        sum(len(v) for v in results.values()),
    )
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    """CLI entry point for the Print Hub scraper."""
    parser = argparse.ArgumentParser(
        description="Download race data from thedogs.com.au Print Hub",
    )
    parser.add_argument(
        "--date",
        default=datetime.now(AEST).strftime("%Y-%m-%d"),
        help="Date to download (YYYY-MM-DD, default: today AEST)",
    )
    parser.add_argument(
        "--venue",
        default=None,
        help="Filter to a specific venue (case-insensitive partial match)",
    )
    parser.add_argument(
        "--output-dir",
        default="./downloads/",
        help="Output directory (default: ./downloads/)",
    )
    parser.add_argument(
        "--list-venues",
        action="store_true",
        help="List available venues and exit (no downloads)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.list_venues:
        venues = list_available_venues(args.date)
        if venues:
            print(f"\nAvailable venues for {args.date}:")
            for v in venues:
                print(f"  - {v}")
        else:
            print(f"No venues found for {args.date}")
        return

    results = scrape_print_hub(args.date, args.output_dir, args.venue)

    if results:
        print(f"\nDownload summary for {args.date}:")
        for venue, files in results.items():
            print(f"  {venue}:")
            for ftype, fpath in files.items():
                print(f"    {ftype}: {fpath}")
    else:
        print(f"No files downloaded for {args.date}")


if __name__ == "__main__":
    main()
