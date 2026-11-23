"""Typed inputs/outputs for each agent.

The LLM is constrained to these schemas (Ollama `format`), and the reply is
validated again with Pydantic before anything downstream uses it.
"""
from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field

WorkType = Literal[
    "extension",            # Part 1 Class A
    "external_alteration",  # Part 1 Class A (windows, render, cladding, garage conversion)
    "roof_enlargement",     # Part 1 Class B (dormer, hip-to-gable)
    "roof_other",           # Part 1 Class C (rooflights, re-roofing)
    "porch",                # Part 1 Class D
    "outbuilding",          # Part 1 Class E
    "caravan",              # not Part 1: use of land
    "chimney_flue",         # Part 1 Class G
    "solar",                # Part 14 Class A
    "demolition",           # Part 11
    "non_householder",      # out of scope
]

WORK_TYPES: tuple[str, ...] = WorkType.__args__  # type: ignore[attr-defined]

Position = Literal["rear", "side", "side_rear", "front", "unspecified"]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class WorksItem(BaseModel):
    work_type: WorkType
    evidence: str = Field(description="The exact words from the description that describe this work")


class RouterOutput(BaseModel):
    householder: bool = Field(description="false if the site is a school, warehouse, office, shop or block of flats")
    items: list[WorksItem]


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class ExtensionFacts(BaseModel):
    position: Position
    storeys: int | None = Field(description="1 or 2 if the text says so, otherwise null")
    evidence: str = Field(description="The exact words from the description about this extension")


class ExtractorOutput(BaseModel):
    extensions: list[ExtensionFacts]
    dwelling_type: Literal["detached", "semi", "terraced", "flat"] | None = Field(
        description="Only if the text names it, otherwise null"
    )
    cladding: bool = Field(description="true if render, insulation or cladding is applied to external walls")
    cladding_evidence: str | None = None
    rear_depth_m: float | None = Field(description="Only if a depth in metres is written in the text")
    height_m: float | None = Field(description="Only if a height in metres is written in the text")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def llm_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema with $defs inlined and descriptions kept.

    Ollama turns the schema into a grammar; a flat schema without $ref is the
    most portable input across Ollama versions and small models.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(copy.deepcopy(defs[name]))
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)
