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
    # Format date for matching in the HTML
    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        logger.error("Invalid date format: %s", target_date_str)
        return []

    # Generate possible date display formats to match
    day_name = dt.strftime("%a")  # e.g., "Sat"
    day_num = dt.day
    month_name = dt.strftime("%B")  # e.g., "April"
    year = dt.year

    # Common formats: "Sat 11 April 2026", "Saturday 11 April 2026",
    # "11 April 2026", "11/04/2026"
    date_patterns = [
        rf"{day_name}\w*\s+{day_num}\s+{month_name}\s+{year}",
        rf"{day_num}\s+{month_name}\s+{year}",
        rf"{day_num}/{dt.month:02d}/{year}",
        target_date_str,
    ]

    # Find the date section in the HTML
    date_section_start = None
    for pattern in date_patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            date_section_start = m.start()
            break

    if date_section_start is None:
        logger.error(
            "Date section not found on Print Hub page for %s. "
            "The date may not be posted yet.",
            target_date_str,
        )
        return []

    # Find the next date section to bound our search
    next_date_pattern = re.compile(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+\d{1,2}\s+\w+\s+\d{4}",
        re.IGNORECASE,
    )
    next_match = next_date_pattern.search(html, date_section_start + 10)
    date_section_end = next_match.start() if next_match else len(html)

    section_html = html[date_section_start:date_section_end]

    # Parse venue rows from the section
    # Look for venue names and associated download links
    venues = []

    # Pattern to find venue entries with their download links
    # The Print Hub typically has table rows with venue name + download links
    venue_pattern = re.compile(
        r'class="[^"]*venue[^"]*"[^>]*>([^<]+)<',
        re.IGNORECASE,
    )
    venue_matches = venue_pattern.findall(section_html)

    # Also try to find venue links
    venue_link_pattern = re.compile(
        r'href="(/racing/([^/"]+)/[^"]*)"[^>]*>([^<]*)</a>',
        re.IGNORECASE,
    )
    link_matches = venue_link_pattern.findall(section_html)

    # Find all download links in the section
    download_pattern = re.compile(
        r'href="([^"]+\.(csv|pdf|zip))"',
        re.IGNORECASE,
    )
    all_downloads = download_pattern.findall(section_html)

    # Build venue→download mapping by proximity
    # Simple approach: find unique venue names, then associate nearby downloads
    seen_venues = set()
    for match in link_matches:
        venue_name = match[2].strip() or match[1].replace("-", " ").title()
        if venue_name and venue_name not in seen_venues:
            seen_venues.add(venue_name)
            slug = _slugify(venue_name)

            # Find download URLs associated with this venue
            downloads = {}
            for dl_url, dl_ext in all_downloads:
                dl_url_full = dl_url if dl_url.startswith("http") else BASE_URL + dl_url
                dl_lower = dl_url.lower()

                if slug[:4] in dl_lower or venue_name.lower()[:4] in dl_lower:
                    if dl_ext.lower() == "csv":
                        downloads["expert_form_csv"] = dl_url_full
                    elif "hound" in dl_lower:
                        downloads["the_hound_pdf"] = dl_url_full
                    elif "short" in dl_lower or "compact" in dl_lower:
                        downloads["racebook_short"] = dl_url_full
                    elif "long" in dl_lower or "full" in dl_lower:
                        downloads["racebook_long"] = dl_url_full
                    elif "expert" in dl_lower:
                        downloads["expert_form_pdf"] = dl_url_full
                    elif dl_ext.lower() == "pdf" and "expert_form_pdf" not in downloads:
                        downloads["expert_form_pdf"] = dl_url_full

            venues.append({
                "name": venue_name,
                "slug": slug,
                "downloads": downloads,
            })

    # Fallback: if no venues found via links, try extracting from download URLs
    if not venues and all_downloads:
        logger.info(
            "No venue links found, attempting download URL extraction. "
            "Found %d download links in date section.",
            len(all_downloads),
        )

    logger.info(
        "Found %d venues on Print Hub for %s",
        len(venues),
        target_date_str,
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

        for file_type, url in venue["downloads"].items():
            filename = FILE_TYPE_NAMES.get(file_type, f"{file_type}.dat")
            dest = os.path.join(venue_dir, filename)

            if download_file(url, dest):
                venue_results[file_type] = dest
            else:
                logger.warning(
                    "Could not download %s for %s",
                    file_type,
                    venue["name"],
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
