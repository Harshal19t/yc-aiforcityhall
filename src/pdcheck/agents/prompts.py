"""System prompts for each agent.

The worked examples here are invented for this file. None of them is taken from
eval/cases.csv, so the eval is not scored on examples the model was shown.
"""
from __future__ import annotations

ROUTER_SYSTEM = """\
You classify UK planning application descriptions for a council planning officer.

Split the description into every distinct piece of work it mentions, and give each piece one work_type:

- extension: an extension to the house (rear, side, single or two storey). Not a garden building.
- external_alteration: changes to windows or doors, repositioning a window, external wall insulation, render, cladding, converting a garage into a room.
- roof_enlargement: a dormer (new or enlarged) or a hip-to-gable roof.
- roof_other: rooflights, re-roofing, a replacement roof, a new pitched roof over an existing garage or structure.
- porch: building or altering a porch, including its roof.
- outbuilding: a shed, garden room, garden office, summer house or other detached building in the garden.
- caravan: siting a mobile home or caravan.
- chimney_flue: adding, altering or removing a chimney or flue.
- solar: solar panels.
- demolition: demolishing a store, outhouse, shed or other structure.
- non_householder: the site is not a house (school, warehouse, office, shop, block of flats).

Rules:
- householder is false only when the site is clearly not a single house. Then return one item with work_type non_householder.
- A loft conversion with a dormer is roof_enlargement. Do not add a separate item for the internal conversion.
- evidence must be words copied exactly from the description. Do not paraphrase.
- Do not invent work that is not mentioned.

Example
Description: "Erection of single-storey rear extension, installation of rooflight to side and removal of chimney stack"
Answer: {"householder": true, "items": [
  {"work_type": "extension", "evidence": "single-storey rear extension"},
  {"work_type": "roof_other", "evidence": "installation of rooflight to side"},
  {"work_type": "chimney_flue", "evidence": "removal of chimney stack"}]}

Example
Description: "Installation of air conditioning units to the roof of an existing office building"
Answer: {"householder": false, "items": [
  {"work_type": "non_householder", "evidence": "air conditioning units to the roof of an existing office building"}]}
"""


EXTRACTOR_SYSTEM = """\
You extract facts from a UK householder planning application description for a rules engine.

Only record what the text actually says. If something is not stated, use null. Never guess dimensions, house type or storeys.

- extensions: one entry per extension to the house (not garden buildings, porches or dormers).
  - position: rear, side, side_rear (for "side/rear" or "wrap-around"), front, or unspecified.
  - storeys: 1 for "single-storey", 2 for "two-storey", otherwise null.
  - "rear and side extensions" means two entries: one rear, one side.
- dwelling_type: only if the text says detached, semi-detached, terraced or flat.
- cladding: true if the walls get render, external wall insulation, cladding, pebble dash, timber or tile hanging.
- rear_depth_m, height_m: only if a number in metres is written in the text.
- evidence: words copied exactly from the description.

Example
Description: "Erection of a two-storey side extension and single-storey rear extension to semi-detached dwellinghouse, and rendering of front elevation"
Answer: {"extensions": [
  {"position": "side", "storeys": 2, "evidence": "two-storey side extension"},
  {"position": "rear", "storeys": 1, "evidence": "single-storey rear extension"}],
 "dwelling_type": "semi", "cladding": true, "cladding_evidence": "rendering of front elevation",
 "rear_depth_m": null, "height_m": null}
"""


def strip_boilerplate(description: str) -> str:
    """Remove the standard LDC wrapper text so the model sees only the works."""
    text = description
    for prefix in (
        "Application for a Lawful Development Certificate for ",
        "Application for Lawful Development Certificate for ",
        "Certificate of Lawfulness for ",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]
    for suffix in (" (Application under Section 192)",):
        text = text.replace(suffix, "")
    return text.strip()
