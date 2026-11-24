"""Deterministic reader for measurements written in metres.

Used two ways: by the keyword baseline, and by the hybrid pipeline, where it takes precedence
over the LLM's number (small models often leave depth blank or invent it).

Reads only metres ("4 metres deep", "3.5m out", "extend out the back by 3m", "2.8m high").
Feet are deliberately ignored, matching the labelling rubric.
"""
from __future__ import annotations

import re

_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"\s*(?:m|metres|meters|metre)\b"
_DEPTH = re.compile(
    rf"{_NUM}{_UNIT}\s*(?:deep|out|long)\b"            # "4 metres deep", "3.5m out"
    rf"|\b(?:out|by)\s+(?:the\s+back\s+)?(?:by\s+)?{_NUM}{_UNIT}"  # "out the back by 3m"
)
_HEIGHT = re.compile(rf"{_NUM}{_UNIT}\s*high\b")


def read_numbers(text: str, has_extension: bool = True) -> tuple[float | None, float | None]:
    """Return (rear_depth_m, height_m). Depth is only read when the work includes an extension."""
    t = text.lower()
    depth = height = None
    if has_extension:
        m = _DEPTH.search(t)
        if m:
            depth = float(next(g for g in m.groups() if g))
    m = _HEIGHT.search(t)
    if m:
        height = float(m.group(1))
    return depth, height
