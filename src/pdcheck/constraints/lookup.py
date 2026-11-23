"""Constraint lookup: given a WGS-84 lat/lng, return PD constraint flags.

Reads GeoJSON files downloaded by data/download_constraints.py from data/raw/.
All geometry operations use shapely; no geopandas dependency required.

Usage
-----
    from pdcheck.constraints.lookup import ConstraintLookup
    lkp = ConstraintLookup()          # loads files once; reuse across calls
    flags = lkp.lookup(lat=53.38, lng=-1.47)
    # flags.article_2_3_land, flags.article_4, flags.listed

The lookup returns None for a flag when the relevant dataset file is missing
(e.g. not yet downloaded), so callers must handle None as "unknown".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

# Maps each constraint flag to the GeoJSON dataset files that trigger it.
# article_2_3_land is true if the point falls in ANY of its datasets.
_FLAG_DATASETS: dict[str, list[str]] = {
    "article_2_3_land": [
        "conservation-area",
        "national-park",
        "area-of-outstanding-natural-beauty",
    ],
    "article_4": [
        "article-4-direction-area",
    ],
    "listed": [
        "listed-building-outline",
    ],
}


@dataclass
class ConstraintFlags:
    article_2_3_land: bool | None
    article_4: bool | None
    listed: bool | None
    missing_datasets: list[str]


def _load_shapes(path: Path) -> list[Any]:
    """Return a list of shapely geometry objects from a GeoJSON FeatureCollection."""
    with open(path, encoding="utf-8") as fh:
        fc = json.load(fh)
    geometries = []
    for feature in fc.get("features", []):
        geom = feature.get("geometry")
        if geom:
            try:
                geometries.append(shape(geom))
            except Exception:
                pass  # skip malformed geometries
    return geometries


class ConstraintLookup:
    """Loads dataset files once and answers point-in-polygon queries."""

    def __init__(self, raw_dir: Path = RAW_DIR) -> None:
        # {dataset_name: list[shapely geometry] | None (file missing)}
        self._shapes: dict[str, list[Any] | None] = {}
        all_names = {d for datasets in _FLAG_DATASETS.values() for d in datasets}
        for name in all_names:
            path = raw_dir / f"{name}.geojson"
            if path.exists():
                self._shapes[name] = _load_shapes(path)
            else:
                self._shapes[name] = None

    def lookup(self, lat: float, lng: float) -> ConstraintFlags:
        """Return constraint flags for a WGS-84 point (lat, lng)."""
        point = Point(lng, lat)  # shapely uses (x=lng, y=lat)
        missing: list[str] = []
        results: dict[str, bool | None] = {}

        for flag, datasets in _FLAG_DATASETS.items():
            flag_true = False
            flag_unknown = False
            for name in datasets:
                shapes = self._shapes.get(name)
                if shapes is None:
                    flag_unknown = True
                    missing.append(name)
                    continue
                if any(geom.contains(point) for geom in shapes):
                    flag_true = True
                    break
            if flag_true:
                results[flag] = True
            elif flag_unknown:
                results[flag] = None
            else:
                results[flag] = False

        return ConstraintFlags(
            article_2_3_land=results["article_2_3_land"],
            article_4=results["article_4"],
            listed=results["listed"],
            missing_datasets=list(dict.fromkeys(missing)),  # deduplicate, preserve order
        )
