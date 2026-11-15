"""Download constraint datasets from planning.data.gov.uk for Sheffield.

Datasets fetched (all OGL v3):
  - article-4-direction-area
  - conservation-area
  - national-park
  - area-of-outstanding-natural-beauty   (now called "National Landscape")
  - listed-building-outline

Output: data/raw/<dataset>.geojson

Sheffield bounding box (EPSG:4326, approx):
  SW: -1.802, 53.303
  NE: -1.323, 53.504

Usage:
  py data/download_constraints.py
  py data/download_constraints.py --no-bbox   # England-wide (large files)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

RAW_DIR = Path(__file__).parent / "raw"
RAW_DIR.mkdir(exist_ok=True)

# Sheffield bounding box: minlng,minlat,maxlng,maxlat
SHEFFIELD_BBOX = "-1.802,53.303,-1.323,53.504"

DATASETS = [
    "article-4-direction-area",
    "conservation-area",
    "national-park",
    "area-of-outstanding-natural-beauty",
    "listed-building-outline",
]

BASE_URL = "https://www.planning.data.gov.uk/api/v1/geojson"
PAGE_SIZE = 500
PAUSE_S = 1.0  # polite pause between pages


def fetch_dataset(name: str, bbox: str | None) -> dict:
    """Page through the GeoJSON API and return a merged FeatureCollection."""
    features: list[dict] = []
    offset = 0
    while True:
        params: dict = {"dataset": name, "limit": PAGE_SIZE, "offset": offset}
        if bbox:
            params["geometry_reference"] = "EPSG:4326"
            params["bbox"] = bbox
        url = f"{BASE_URL}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": "pd-precheck/0.1 (research project)"})
        try:
            with urlopen(req, timeout=30) as resp:
                page = json.loads(resp.read())
        except HTTPError as e:
            print(f"  HTTP {e.code} on {url}")
            raise
        except URLError as e:
            print(f"  Network error: {e.reason}")
            raise

        batch = page.get("features", [])
        features.extend(batch)
        print(f"  {name}: fetched {len(features)} features (page offset {offset})", flush=True)

        # Stop when we get fewer results than the page size
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(PAUSE_S)

    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-bbox", action="store_true", help="Fetch England-wide (large)")
    args = parser.parse_args()

    bbox = None if args.no_bbox else SHEFFIELD_BBOX

    for name in DATASETS:
        out_path = RAW_DIR / f"{name}.geojson"
        print(f"Fetching {name} ({'Sheffield bbox' if bbox else 'England-wide'}) …")
        try:
            fc = fetch_dataset(name, bbox)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        out_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")
        print(f"  Saved {len(fc['features'])} features → {out_path.relative_to(Path.cwd())}")

    print("\nDone. Update data/SOURCES.md with today's retrieval date.")


if __name__ == "__main__":
    main()
