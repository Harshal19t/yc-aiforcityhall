"""Tests for the constraint lookup module.

Uses a temporary directory with synthetic GeoJSON fixtures so tests run
without the real downloaded datasets.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pdcheck.constraints.lookup import ConstraintLookup, ConstraintFlags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_geojson(directory: Path, name: str, polygons: list[list[list[float]]]) -> None:
    """Write a simple FeatureCollection with Polygon features."""
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
            "properties": {},
        }
        for ring in polygons
    ]
    path = directory / f"{name}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


# A small square centred on Sheffield city centre (lng -1.47, lat 53.38)
# Coordinates are [lng, lat] as GeoJSON requires.
_SHEFFIELD_SQUARE = [
    [-1.48, 53.37],
    [-1.46, 53.37],
    [-1.46, 53.39],
    [-1.48, 53.39],
    [-1.48, 53.37],
]

# A square well away from Sheffield
_LONDON_SQUARE = [
    [-0.12, 51.49],
    [-0.10, 51.49],
    [-0.10, 51.51],
    [-0.12, 51.51],
    [-0.12, 51.49],
]

INSIDE_SHEFFIELD = (53.38, -1.47)   # (lat, lng)
OUTSIDE_SHEFFIELD = (51.50, -0.11)  # London


# ---------------------------------------------------------------------------
# Tests: missing datasets → all None
# ---------------------------------------------------------------------------

def test_all_none_when_no_files():
    with tempfile.TemporaryDirectory() as tmp:
        lkp = ConstraintLookup(raw_dir=Path(tmp))
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    assert flags.article_2_3_land is None
    assert flags.article_4 is None
    assert flags.listed is None
    assert len(flags.missing_datasets) > 0


# ---------------------------------------------------------------------------
# Tests: point inside a conservation area → article_2_3_land True
# ---------------------------------------------------------------------------

def test_conservation_area_inside():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "conservation-area", [_SHEFFIELD_SQUARE])
        # Provide empty files for the others so they don't count as missing
        for name in ["national-park", "area-of-outstanding-natural-beauty",
                     "article-4-direction-area", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    assert flags.article_2_3_land is True
    assert flags.missing_datasets == []


def test_conservation_area_outside():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "conservation-area", [_SHEFFIELD_SQUARE])
        for name in ["national-park", "area-of-outstanding-natural-beauty",
                     "article-4-direction-area", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*OUTSIDE_SHEFFIELD)
    assert flags.article_2_3_land is False


# ---------------------------------------------------------------------------
# Tests: article 4 direction
# ---------------------------------------------------------------------------

def test_article_4_inside():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "article-4-direction-area", [_SHEFFIELD_SQUARE])
        for name in ["conservation-area", "national-park",
                     "area-of-outstanding-natural-beauty", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    assert flags.article_4 is True


def test_article_4_outside():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "article-4-direction-area", [_SHEFFIELD_SQUARE])
        for name in ["conservation-area", "national-park",
                     "area-of-outstanding-natural-beauty", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*OUTSIDE_SHEFFIELD)
    assert flags.article_4 is False


# ---------------------------------------------------------------------------
# Tests: listed building
# ---------------------------------------------------------------------------

def test_listed_inside():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "listed-building-outline", [_SHEFFIELD_SQUARE])
        for name in ["conservation-area", "national-park",
                     "area-of-outstanding-natural-beauty", "article-4-direction-area"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    assert flags.listed is True


# ---------------------------------------------------------------------------
# Tests: article_2_3_land triggered by national park, not conservation area
# ---------------------------------------------------------------------------

def test_national_park_triggers_article_2_3():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write_geojson(d, "national-park", [_SHEFFIELD_SQUARE])
        for name in ["conservation-area", "area-of-outstanding-natural-beauty",
                     "article-4-direction-area", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    assert flags.article_2_3_land is True


# ---------------------------------------------------------------------------
# Tests: partial missing → flag is None, others resolve normally
# ---------------------------------------------------------------------------

def test_partial_missing_article_2_3():
    """conservation-area present, national-park missing → article_2_3_land is None
    (can't confirm absence without all datasets)."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # Only conservation-area present, national-park and AONB missing
        _write_geojson(d, "conservation-area", [_LONDON_SQUARE])  # outside Sheffield
        for name in ["article-4-direction-area", "listed-building-outline"]:
            _write_geojson(d, name, [])
        lkp = ConstraintLookup(raw_dir=d)
        flags = lkp.lookup(*INSIDE_SHEFFIELD)
    # conservation-area says False for Sheffield, but other datasets are missing
    assert flags.article_2_3_land is None
    assert "national-park" in flags.missing_datasets
