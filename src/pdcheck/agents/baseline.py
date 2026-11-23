"""Keyword baseline: a drop-in replacement for the LLM, built from the rubric's
own trigger words. It exists so the eval can answer "does the LLM beat simple
keyword matching?". The word lists come from docs/labelling_rubric.md and were
not tuned on eval cases.
"""
from __future__ import annotations

import re
from typing import Any

from pdcheck.llm.client import LLMResponse

_NON_HOUSEHOLDER = ["school", "warehouse", "office building", "shop", "academy", "college", "block of flats",
                    "apartments", "use class"]

_WORK_KEYWORDS: list[tuple[str, list[str]]] = [
    ("extension", ["rear extension", "side extension", "side/rear extension", "storey extension",
                   "extension to dwelling", "rear and side extension", "rear extensions"]),
    ("external_alteration", ["fenestration", "window", "external wall insulation", "render", "cladding",
                             "garage to form", "conversion of integral garage", "conversion of garage"]),
    ("roof_enlargement", ["dormer", "hip to gable", "hip-to-gable"]),
    ("roof_other", ["rooflight", "roof light", "re-roof", "replacement roof", "pitched roof over"]),
    ("porch", ["porch"]),
    ("outbuilding", ["outbuilding", "shed", "garden room", "garden office", "summer house"]),
    ("caravan", ["mobile home", "caravan"]),
    ("chimney_flue", ["chimney", "flue"]),
    ("solar", ["solar"]),
    ("demolition", ["demolition"]),
]


def _router(text: str) -> dict[str, Any]:
    t = text.lower()
    hit = next((w for w in _NON_HOUSEHOLDER if w in t), None)
    if hit:
        return {"householder": False, "items": [{"work_type": "non_householder", "evidence": hit}]}
    items = []
    for wt, words in _WORK_KEYWORDS:
        w = next((w for w in words if w in t), None)
        if w:
            items.append({"work_type": wt, "evidence": w})
    return {"householder": True, "items": items}


def _extractor(text: str) -> dict[str, Any]:
    t = text.lower()
    extensions = []
    storeys = 1 if "single-storey" in t or "single storey" in t else (2 if "two-storey" in t else None)
    if "side/rear extension" in t:
        extensions.append({"position": "side_rear", "storeys": storeys, "evidence": "side/rear extension"})
    else:
        if re.search(r"rear (and side )?extension", t):
            extensions.append({"position": "rear", "storeys": storeys, "evidence": "rear"})
        if re.search(r"(rear and )?side extension|and side extensions", t):
            extensions.append({"position": "side", "storeys": storeys, "evidence": "side"})
    dwelling = next((d for k, d in [("semi-detached", "semi"), ("terraced", "terraced"),
                                    ("detached", "detached"), ("flat", "flat")] if k in t), None)
    clad_word = next((w for w in ["render", "external wall insulation", "cladding", "pebble dash"] if w in t), None)
    return {"extensions": extensions, "dwelling_type": dwelling, "cladding": clad_word is not None,
            "cladding_evidence": clad_word, "rear_depth_m": None, "height_m": None}


class KeywordClient:
    """Implements the LLMClient protocol with keyword rules instead of a model."""

    model = "keyword-baseline"

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        text = user.split('Description: "', 1)[-1].rsplit('"', 1)[0]
        data = _router(text) if "classify" in system else _extractor(text)
        return LLMResponse(data=data, model=self.model, cached=True, latency_ms=0)
