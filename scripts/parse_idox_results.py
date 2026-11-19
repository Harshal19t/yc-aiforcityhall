#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
#   "lxml>=5",
#   "pdfplumber>=0.11",
# ]
# ///
"""
parse_idox_results.py
~~~~~~~~~~~~~~~~~~~~~
Parse saved Sheffield IDOX PublicAccess search-results HTML into eval/cases.csv.

Usage
-----
1. In Chrome, go to Sheffield PublicAccess, run an Advanced Search filtered to
   "Certificate of Lawful Use Proposed Dev" with status "Decided".
2. File → Save As → "Web Page, Complete" for each paginated results page.
   Name them e.g. results_p1.html, results_p2.html, …
3. Run:
       python scripts/parse_idox_results.py path/to/results_*.html

   Or for a whole directory:
       python scripts/parse_idox_results.py --dir path/to/saved_pages/

Output
------
eval/cases.csv  (appends; skips duplicates by case_id)

Also handles individual case-detail pages saved with File → Save As, and
decision-notice PDFs via pdfplumber (--pdf flag).

Requirements
------------
    pip install beautifulsoup4 lxml pdfplumber
"""

import argparse
import csv
import glob
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "eval" / "cases.csv"

CSV_FIELDNAMES = [
    "case_id",
    "council",
    "address",
    "proposal_text",
    "dwelling_type",
    "extension_position",
    "storeys",
    "rear_depth_m",
    "height_m",
    "article_2_3_land",
    "article_4",
    "listed",
    "real_outcome",
    "decision_date",
    "source_ref",
    "labelled_by",
    "notes",
]

COUNCIL = "Sheffield"


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def load_existing_ids(csv_path: Path) -> set:
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["case_id"] for row in reader}


def append_rows(csv_path: Path, rows: list[dict]) -> int:
    """Append rows to CSV, writing header if file is new. Returns count written."""
    write_header = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        for row in rows:
            # Fill any missing fields with empty string
            full_row = {k: row.get(k, "") for k in CSV_FIELDNAMES}
            writer.writerow(full_row)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Decision normaliser
# ---------------------------------------------------------------------------

GRANT_PATTERNS = re.compile(
    r"\b(grant|granted|lawful|approved|permit|permitted|certificate issued)\b",
    re.IGNORECASE,
)
REFUSE_PATTERNS = re.compile(
    r"\b(refus|refused|reject|rejected|unlawful|not lawful|not granted|declined)\b",
    re.IGNORECASE,
)


def normalise_decision(raw: str) -> str:
    """Return 'lawful', 'not_lawful', or '' (unknown)."""
    raw = raw.strip()
    if GRANT_PATTERNS.search(raw):
        return "lawful"
    if REFUSE_PATTERNS.search(raw):
        return "not_lawful"
    return ""


# ---------------------------------------------------------------------------
# IDOX search-results page parser
# ---------------------------------------------------------------------------

def parse_search_results_html(html: str) -> list[dict]:
    """
    Parse a Sheffield IDOX search-results page.

    Sheffield's IDOX (planningapps.sheffield.gov.uk) renders results as:
      <ul id="searchresults">
        <li class="searchresult"> … </li>
      </ul>

    Falls back to class-based ul and then table layouts for other councils.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Missing dependency: pip install beautifulsoup4 lxml")

    soup = BeautifulSoup(html, "lxml")
    rows = []

    # --- Layout A: Sheffield IDOX — <ul id="searchresults"> ------------------
    result_list = (
        soup.find("ul", id="searchresults")
        or soup.find("ul", id=re.compile(r"searchresult", re.I))
        or soup.find("ul", class_=re.compile(r"searchresult", re.I))
    )
    if result_list:
        for li in result_list.find_all("li", class_="searchresult"):
            row = _parse_li_result(li)
            if row:
                rows.append(row)
        return rows

    # --- Layout B: <table> ---------------------------------------------------
    table = soup.find("table", class_=re.compile(r"result", re.I))
    if table is None:
        table = soup.find("table")
    if table:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            row = _parse_table_row(cells, headers)
            if row:
                rows.append(row)
        return rows

    return rows


def _parse_li_result(li) -> dict | None:
    """
    Parse a single <li class="searchresult"> from Sheffield's IDOX portal.

    Actual structure observed:
      <a class="summaryLink" href="https://planningapps.sheffield.gov.uk/...">
        <div class="summaryLinkTextClamp">Proposal text here</div>
      </a>
      <p class="address">19 Chelsea Road Sheffield S11 9BQ</p>
      <p class="metaInfo">
        Ref. No: 26/03072/LD2
        · Received: Wed 14 Oct 2026
        · Validated: Wed 14 Oct 2026
      </p>
      <div class="badges">
        <div class="badge-status"><div class="value">Decided</div></div>
      </div>

    Note: decision (Granted/Refused) is NOT on the results page — only
    "Decided" status is shown. real_outcome will be filled as '' and must
    be populated from the case-detail page or PDF.
    """
    # --- Proposal text (inside summaryLink > summaryLinkTextClamp) -----------
    summary_link = li.find("a", class_="summaryLink")
    if summary_link is None:
        return None

    detail_url = summary_link.get("href", "")

    clamp = summary_link.find(class_="summaryLinkTextClamp")
    proposal = clamp.get_text(" ", strip=True) if clamp else summary_link.get_text(" ", strip=True)

    # --- Address -------------------------------------------------------------
    addr_tag = li.find("p", class_="address")
    address = addr_tag.get_text(" ", strip=True) if addr_tag else ""

    # --- Reference number (inside metaInfo paragraph) -----------------------
    meta_tag = li.find("p", class_="metaInfo")
    meta_text = meta_tag.get_text(" ", strip=True) if meta_tag else ""
    case_id = _extract_ref(meta_text)

    # Received / Validated dates from metaInfo
    decision_date = ""
    m = re.search(r"Validated:\s*\w+\s+(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})", meta_text)
    if m:
        decision_date = m.group(1)

    # --- Decision: not on results page, leave blank -------------------------
    # The badge only says "Decided"; actual Grant/Refuse is on the detail page.
    real_outcome = ""

    # Try to pull from badge just in case a future IDOX version adds it
    badge_val = li.find(class_="badge-status")
    if badge_val:
        val_div = badge_val.find(class_="value")
        if val_div:
            real_outcome = normalise_decision(val_div.get_text(strip=True))

    if not case_id:
        # Last resort: extract from URL keyVal param won't give a ref,
        # so skip rows with no parseable reference.
        return None

    return {
        "case_id": case_id,
        "council": COUNCIL,
        "address": address,
        "proposal_text": proposal,
        "real_outcome": real_outcome,
        "decision_date": decision_date,
        "source_ref": detail_url,
        "labelled_by": "idox_scraper",
    }


def _parse_table_row(cells, headers: list) -> dict | None:
    """Parse a <tr> from a results table when IDOX uses tabular layout."""
    def cell(name: str) -> str:
        for alias in (name, name.replace(" ", ""), name.replace("_", " ")):
            for i, h in enumerate(headers):
                if alias in h and i < len(cells):
                    return cells[i].get_text(" ", strip=True)
        return ""

    ref = cell("reference") or cell("ref") or (cells[0].get_text(strip=True) if cells else "")
    case_id = _extract_ref(ref) or ref[:30]
    address = cell("address") or cell("location")
    proposal = cell("proposal") or cell("description")
    raw_decision = cell("decision") or cell("status")
    decision_date = _extract_date(cell("date") or cell("decision date"))
    real_outcome = normalise_decision(raw_decision)

    # Try to get source link
    source_ref = ""
    for td in cells:
        a = td.find("a")
        if a and a.get("href"):
            href = a["href"]
            if "caseNumber" in href or "id=" in href:
                source_ref = (
                    href if href.startswith("http")
                    else "http://publicaccess.sheffield.gov.uk" + href
                )
                break

    if not case_id:
        return None

    return {
        "case_id": case_id,
        "council": COUNCIL,
        "address": address,
        "proposal_text": proposal,
        "real_outcome": real_outcome,
        "decision_date": decision_date,
        "source_ref": source_ref,
        "labelled_by": "idox_scraper",
    }


# ---------------------------------------------------------------------------
# Case-detail page parser (optional — richer proposal text)
# ---------------------------------------------------------------------------

def parse_case_detail_html(html: str) -> dict | None:
    """
    Parse a saved case-detail page (the page you get after clicking a result).

    Extracts: case_id, address, proposal, decision, decision_date.
    Returns None if the page doesn't look like an IDOX detail page.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Missing dependency: pip install beautifulsoup4 lxml")

    soup = BeautifulSoup(html, "lxml")

    # IDOX detail pages have a <span id="caseNumber"> or similar
    def find_text(id_or_class: str) -> str:
        tag = soup.find(id=re.compile(id_or_class, re.I))
        if tag:
            return tag.get_text(" ", strip=True)
        tag = soup.find(class_=re.compile(id_or_class, re.I))
        return tag.get_text(" ", strip=True) if tag else ""

    # Try the definition list layout IDOX uses for case details
    # <dt>Application Reference:</dt><dd>26/00123/LD2</dd>
    details = {}
    for dt in soup.find_all("dt"):
        key = dt.get_text(strip=True).rstrip(":").lower()
        dd = dt.find_next_sibling("dd")
        if dd:
            details[key] = dd.get_text(" ", strip=True)

    case_id = (
        details.get("application reference")
        or details.get("reference")
        or details.get("app ref")
        or find_text("caseNumber")
    )
    if not case_id:
        return None
    case_id = _extract_ref(case_id) or case_id

    address = (
        details.get("site address")
        or details.get("address")
        or details.get("location")
        or find_text("address")
    )
    proposal = (
        details.get("proposal")
        or details.get("description")
        or details.get("development description")
        or find_text("proposal")
    )
    raw_decision = (
        details.get("decision")
        or details.get("decision type")
        or details.get("status")
        or ""
    )
    real_outcome = normalise_decision(raw_decision)
    decision_date = _extract_date(
        details.get("decision issued date")
        or details.get("decision date")
        or details.get("date of decision")
        or ""
    )

    return {
        "case_id": case_id,
        "council": COUNCIL,
        "address": address,
        "proposal_text": proposal,
        "real_outcome": real_outcome,
        "decision_date": decision_date,
        "source_ref": "",
        "labelled_by": "idox_detail_scraper",
    }


# ---------------------------------------------------------------------------
# PDF decision-notice parser
# ---------------------------------------------------------------------------

def parse_decision_pdf(pdf_path: str) -> dict:
    """
    Extract fields from a Sheffield LDC decision notice PDF.

    Returns a partial row dict — merge with the CSV row for this case.
    Fields extracted: case_id, real_outcome, decision_date, notes.
    """
    try:
        import pdfplumber
    except ImportError:
        sys.exit("Missing dependency: pip install pdfplumber")

    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    case_id = ""
    m = re.search(r"\b(\d{2}/\d{5}/LD[CP2]?\d*)\b", text)
    if m:
        case_id = m.group(1)

    real_outcome = normalise_decision(text[:2000])  # decision usually on first pages

    decision_date = ""
    for pattern in (
        r"Date[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        r"(\d{1,2}\s+\w+\s+\d{4})",   # e.g. "15 June 2026"
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            decision_date = m.group(1).strip()
            break

    # Look for explicit measurements in the PDF text
    notes_parts = []

    # Rear extension depth
    m = re.search(
        r"(?:depth|projection|extend[s]?)[^\d]{0,20}(\d+(?:\.\d+)?)\s*m(?:etre)?",
        text, re.IGNORECASE,
    )
    if m:
        notes_parts.append(f"depth={m.group(1)}m")

    # Ridge/height
    m = re.search(
        r"(?:height|ridge)[^\d]{0,20}(\d+(?:\.\d+)?)\s*m(?:etre)?",
        text, re.IGNORECASE,
    )
    if m:
        notes_parts.append(f"height={m.group(1)}m")

    # Eaves
    m = re.search(
        r"eaves[^\d]{0,20}(\d+(?:\.\d+)?)\s*m(?:etre)?",
        text, re.IGNORECASE,
    )
    if m:
        notes_parts.append(f"eaves={m.group(1)}m")

    return {
        "case_id": case_id,
        "real_outcome": real_outcome,
        "decision_date": decision_date,
        "notes": "; ".join(notes_parts) if notes_parts else "",
    }


# ---------------------------------------------------------------------------
# Small text utilities
# ---------------------------------------------------------------------------

SHEFFIELD_REF_RE = re.compile(r"\b(\d{2}/\d{5}/[A-Z0-9]+)\b")


def _extract_ref(text: str) -> str:
    m = SHEFFIELD_REF_RE.search(text)
    return m.group(1) if m else ""


def _extract_address(text: str) -> str:
    """Pull address from a string like '26/00123/LD2 - 10 Foo Road, Sheffield'."""
    parts = re.split(r"\s*[-–]\s*", text, maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _extract_date(text: str) -> str:
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else text.strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse Sheffield IDOX search-results HTML into eval/cases.csv"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Saved HTML files (glob-expanded by shell, or pass individually)",
    )
    parser.add_argument(
        "--dir",
        help="Directory of saved HTML files (all *.html inside)",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Parse as case-detail pages rather than search-results pages",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Parse as decision-notice PDFs (uses pdfplumber)",
    )
    parser.add_argument(
        "--out",
        default=str(CSV_PATH),
        help=f"Output CSV path (default: {CSV_PATH})",
    )
    args = parser.parse_args()

    # Collect file paths
    paths: list[str] = list(args.files)
    if args.dir:
        ext = "*.pdf" if args.pdf else "*.html"
        paths += glob.glob(os.path.join(args.dir, ext))
    if not paths:
        parser.print_help()
        sys.exit(1)

    out_path = Path(args.out)
    existing_ids = load_existing_ids(out_path)
    new_rows: list[dict] = []
    skipped = 0

    for path in paths:
        print(f"  Parsing {path} ...", end=" ")
        try:
            if args.pdf:
                row = parse_decision_pdf(path)
                rows = [row] if row.get("case_id") else []
            else:
                with open(path, encoding="utf-8", errors="replace") as f:
                    html = f.read()
                if args.detail:
                    row = parse_case_detail_html(html)
                    rows = [row] if row else []
                else:
                    rows = parse_search_results_html(html)

            page_new = 0
            for row in rows:
                cid = row.get("case_id", "").strip()
                if not cid or cid in existing_ids:
                    skipped += 1
                    continue
                existing_ids.add(cid)
                new_rows.append(row)
                page_new += 1
            print(f"{page_new} new cases")
        except Exception as exc:
            print(f"ERROR: {exc}")

    try:
        written = append_rows(out_path, new_rows)
    except PermissionError:
        print(
            f"\nPermission denied writing to {out_path}\n"
            "  → Close the file in Excel (or any other app) and try again."
        )
        sys.exit(1)
    print(f"\nDone. {written} rows written → {out_path}  ({skipped} skipped / duplicates)")

    if written == 0 and not new_rows:
        print(
            "\nNo rows extracted. Possible causes:\n"
            "  • The HTML uses a different IDOX layout — open the file and check the\n"
            "    structure around the results list (look for <ul class='searchresults'>\n"
            "    or a results <table>).\n"
            "  • You saved only the outer frame page — try File → Save As →\n"
            "    'Web Page, Complete' (not 'Web Page, HTML Only').\n"
            "  • The page requires JavaScript rendering — in that case, use\n"
            "    the --detail flag on individual case pages, which are static."
        )


if __name__ == "__main__":
    main()
