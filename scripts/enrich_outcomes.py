#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
#   "lxml>=5",
#   "requests>=2.31",
#   "requests-toolbelt>=1.0",
#   "pip-system-certs>=4.0",
# ]
# ///
"""
enrich_outcomes.py
~~~~~~~~~~~~~~~~~~
Read eval/cases.csv, fetch each source_ref detail page, extract the
Decision field, and write real_outcome back to the CSV.

Usage
-----
    uv run scripts/enrich_outcomes.py

Options
-------
    --dry-run   Print what would be written without saving
    --limit N   Only process first N rows (useful for testing)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

# pip-system-certs patches requests to use the Windows certificate store
# automatically — no other code changes needed.
try:
    import pip_system_certs.wrapt_requests  # noqa: F401
except ImportError:
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "eval" / "cases.csv"

GRANT_KEYWORDS = ("grant", "lawful", "certificate issued", "approved")
REFUSE_KEYWORDS = ("refus", "unlawful", "not lawful", "not granted", "reject")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def normalise(raw: str) -> str:
    low = raw.lower()
    if any(k in low for k in GRANT_KEYWORDS):
        return "lawful"
    if any(k in low for k in REFUSE_KEYWORDS):
        return "not_lawful"
    return ""


def scrape_decision(url: str) -> tuple[str, str]:
    """
    Fetch a Sheffield IDOX case-detail page and return (raw_decision, real_outcome).

    The detail page has a <dl> of key/value pairs:
      <dt>Decision:</dt>
      <dd>Grant Certificate of Lawful Use Dev</dd>
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as e:
        return "", f"ERROR: {e.response.status_code} {e}"
    except requests.RequestException as e:
        return "", f"ERROR: {e}"

    soup = BeautifulSoup(resp.text, "lxml")

    # Primary: look for <dt> containing "Decision" followed by <dd>
    for dt in soup.find_all("dt"):
        if "decision" in dt.get_text(strip=True).lower():
            dd = dt.find_next_sibling("dd")
            if dd:
                raw = dd.get_text(" ", strip=True)
                return raw, normalise(raw)

    # Fallback: search any element whose text contains grant/refuse keywords
    for tag in soup.find_all(["span", "td", "p", "div"]):
        txt = tag.get_text(" ", strip=True)
        if len(txt) < 80 and normalise(txt):
            return txt, normalise(txt)

    return "", ""


def main():
    parser = argparse.ArgumentParser(description="Enrich cases.csv with real_outcome from detail pages")
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N rows")
    parser.add_argument("--csv", default=str(CSV_PATH), help=f"CSV path (default: {CSV_PATH})")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []

    updated = 0
    errors = 0

    for i, row in enumerate(rows):
        if args.limit and i >= args.limit:
            break

        # Skip if already filled
        if row.get("real_outcome") in ("lawful", "not_lawful"):
            print(f"  [{i+1:>3}] {row['case_id']}  already set → {row['real_outcome']}")
            continue

        url = row.get("source_ref", "").strip()
        if not url:
            print(f"  [{i+1:>3}] {row['case_id']}  no source_ref — skipping")
            continue

        print(f"  [{i+1:>3}] {row['case_id']}  fetching ...", end=" ", flush=True)

        # Retry up to 3 times with exponential backoff on 429 / connection errors
        raw, outcome = "", ""
        for attempt in range(3):
            raw, outcome = scrape_decision(url)
            if "429" in outcome or "Too Many" in outcome or "RemoteDisconnected" in outcome:
                wait = 30 * (attempt + 1)
                print(f"rate-limited, waiting {wait}s ...", end=" ", flush=True)
                time.sleep(wait)
            else:
                break

        print(f"{raw!r:50s} → {outcome}")

        if outcome.startswith("ERROR"):
            errors += 1
        elif outcome:
            row["real_outcome"] = outcome
            updated += 1

        time.sleep(10)  # 10s between requests — portal rate-limits aggressively

    print(f"\n{updated} rows updated, {errors} errors")

    if args.dry_run:
        print("(dry run — not saved)")
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved → {csv_path}")


if __name__ == "__main__":
    main()
