"""Keyword baseline (v2): a drop-in replacement for the LLM, built from plain keyword and
regex rules. It exists so the eval can answer "does the LLM beat simple rules?".

Version history (disclosed in the README):
  v1  keyword lists from docs/labelling_rubric.md, written after reading the Sheffield cases.
  v2.1 fixed a regex bug (\"about 2.5m\" matched \"out\") and only reads depth when an extension is present;
       the number reader now lives in numbers.py and is shared with the hybrid pipeline.
  v2  made BEFORE running anything on eval/messy_cases.csv, so the baseline is not a strawman:
      number extraction ("4 metres deep"), "back" = rear, "extend" counts as an extension,
      "insulation", "flat roof" is not a flat, and a few obvious non-householder words
      (pub, hotel, restaurant).
Deliberately NOT handled: negation ("no dormer"), feet/inches, wrap-around vs two separate
extensions. These are the kinds of thing a rule list gets wrong and a language model should not.
"""
from __future__ import annotations

import re
from typing import Any

from pdcheck.agents.numbers import read_numbers
from pdcheck.llm.client import LLMResponse

_NON_HOUSEHOLDER = ["school", "warehouse", "office building", "shop", "academy", "college", "block of flats",
                    "apartments", "use class", "pub", "hotel", "restaurant"]

_WORK_KEYWORDS: list[tuple[str, list[str]]] = [
    ("extension", ["extension", "extend"]),
    ("external_alteration", ["fenestration", "window", "external wall insulation", "insulation", "render",
                             "cladding", "garage to form", "conversion of integral garage",
                             "conversion of garage", "convert the integral garage", "bay window", "front door"]),
    ("roof_enlargement", ["dormer", "hip to gable", "hip-to-gable"]),
    ("roof_other", ["rooflight", "roof light", "re-roof", "replacement roof", "pitched roof over", "velux"]),
    ("porch", ["porch"]),
    ("outbuilding", ["outbuilding", "shed", "garden room", "garden office", "summer house", "summerhouse"]),
    ("caravan", ["mobile home", "caravan"]),
    ("chimney_flue", ["chimney", "flue"]),
    ("solar", ["solar"]),
    ("demolition", ["demolition", "demolish", "knock down", "take down the old"]),
]

def _word(t: str, w: str) -> bool:
    return re.search(rf"\b{re.escape(w)}", t) is not None


def _router(text: str) -> dict[str, Any]:
    t = text.lower()
    hit = next((w for w in _NON_HOUSEHOLDER if _word(t, w)), None)
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
    storeys = None
    if re.search(r"single[- ]storey|ground floor only", t):
        storeys = 1
    elif re.search(r"two[- ]storey|double[- ]storey", t):
        storeys = 2

    extensions = []
    if re.search(r"extension|extend", t):
        if "side/rear" in t or "wrap" in t:
            extensions.append({"position": "side_rear", "storeys": storeys, "evidence": "side/rear"})
        else:
            has_rear = re.search(r"\b(rear|back)\b", t) is not None
            has_side = re.search(r"\bside\b", t) is not None
            if has_rear:
                extensions.append({"position": "rear", "storeys": storeys, "evidence": "rear"})
            if has_side:
                extensions.append({"position": "side", "storeys": storeys, "evidence": "side"})
            if not extensions:
                extensions.append({"position": "unspecified", "storeys": storeys, "evidence": "extension"})

    dwelling = None
    for pat, d in [(r"semi[- ]?detached", "semi"), (r"terrace", "terraced"),
                   (r"\bdetached", "detached"), (r"\bflat\b(?! roof)", "flat")]:
        if re.search(pat, t):
            dwelling = d
            break

    depth, height = read_numbers(text, has_extension=bool(extensions))

    clad_word = next((w for w in ["render", "external wall insulation", "insulation", "cladding", "pebble dash"]
                      if w in t), None)
    return {"extensions": extensions, "dwelling_type": dwelling, "cladding": clad_word is not None,
            "cladding_evidence": clad_word, "rear_depth_m": depth, "height_m": height}


class KeywordClient:
    """Implements the LLMClient protocol with keyword rules instead of a model."""

    model = "keyword-baseline"

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        text = user.split('Description: "', 1)[-1].rsplit('"', 1)[0]
        data = _router(text) if "classify" in system else _extractor(text)
        return LLMResponse(data=data, model=self.model, cached=True, latency_ms=0)
