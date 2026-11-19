"""FastAPI application — householder PD pre-check API.

Endpoints
---------
POST /check
    Takes proposal fields + optional lat/lng.
    Runs constraint lookup (if lat/lng supplied) then the rule engine.
    Returns status, findings, other_consents, unknown_fields.

GET /health
    Liveness probe.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pdcheck.check.engine import Proposal, evaluate
from pdcheck.constraints.lookup import ConstraintLookup

app = FastAPI(
    title="PD Pre-check API",
    description="Deterministic householder permitted development checker (GPDO 2015 Sch 2 Pt 1 Class A)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load constraint lookup once at startup (reads GeoJSON files)
_lookup = ConstraintLookup()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CheckRequest(BaseModel):
    # Location (optional — used for constraint lookup)
    lat: float | None = Field(None, description="WGS-84 latitude")
    lng: float | None = Field(None, description="WGS-84 longitude")

    # Proposal fields — mirrors Proposal dataclass
    dwelling_type: str | None = Field(None, description="detached | semi | terraced | flat")
    extension_position: str | None = Field(None, description="rear | side | front")
    storeys: int | None = None
    height_m: float | None = None
    eaves_height_m: float | None = None
    rear_depth_m: float | None = None
    distance_to_boundary_m: float | None = None
    side_width_ratio: float | None = Field(None, description="Extension width / original house width")
    curtilage_cover_ratio: float | None = None
    exceeds_highest_roof: bool | None = None
    exceeds_existing_eaves: bool | None = None
    beyond_principal_elevation: bool | None = None
    cladding: bool | None = None
    distance_to_rear_boundary_m: float | None = None
    permitted_use_only: bool | None = None
    built_under_part_20: bool | None = None
    includes_verandah_balcony_platform: bool | None = None
    includes_chimney_flue: bool | None = None
    includes_roof_alteration: bool | None = None

    # Constraint overrides (ignored if lat/lng supplied — lookup wins)
    article_2_3_land: bool | None = None
    article_4: bool | None = None
    listed: bool | None = None


class FindingOut(BaseModel):
    rule_id: str
    outcome: str
    description: str
    citation: str
    verify: bool


class ConstraintInfo(BaseModel):
    article_2_3_land: bool | None
    article_4: bool | None
    listed: bool | None
    missing_datasets: list[str]
    source: str  # "lookup" | "manual" | "unknown"


class CheckResponse(BaseModel):
    status: str
    findings: list[FindingOut]
    other_consents: list[FindingOut]
    unknown_fields: list[str]
    constraints: ConstraintInfo


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check(req: CheckRequest) -> Any:
    # --- 1. Constraint lookup ------------------------------------------------
    if req.lat is not None and req.lng is not None:
        flags = _lookup.lookup(lat=req.lat, lng=req.lng)
        constraint_info = ConstraintInfo(
            article_2_3_land=flags.article_2_3_land,
            article_4=flags.article_4,
            listed=flags.listed,
            missing_datasets=flags.missing_datasets,
            source="lookup",
        )
    else:
        # Fall back to manually supplied values
        constraint_info = ConstraintInfo(
            article_2_3_land=req.article_2_3_land,
            article_4=req.article_4,
            listed=req.listed,
            missing_datasets=[],
            source="manual" if any(
                v is not None for v in [req.article_2_3_land, req.article_4, req.listed]
            ) else "unknown",
        )

    # --- 2. Build Proposal ---------------------------------------------------
    p = Proposal(
        dwelling_type=req.dwelling_type,
        extension_position=req.extension_position,
        storeys=req.storeys,
        height_m=req.height_m,
        eaves_height_m=req.eaves_height_m,
        rear_depth_m=req.rear_depth_m,
        distance_to_boundary_m=req.distance_to_boundary_m,
        side_width_ratio=req.side_width_ratio,
        curtilage_cover_ratio=req.curtilage_cover_ratio,
        exceeds_highest_roof=req.exceeds_highest_roof,
        exceeds_existing_eaves=req.exceeds_existing_eaves,
        beyond_principal_elevation=req.beyond_principal_elevation,
        cladding=req.cladding,
        distance_to_rear_boundary_m=req.distance_to_rear_boundary_m,
        permitted_use_only=req.permitted_use_only,
        built_under_part_20=req.built_under_part_20,
        includes_verandah_balcony_platform=req.includes_verandah_balcony_platform,
        includes_chimney_flue=req.includes_chimney_flue,
        includes_roof_alteration=req.includes_roof_alteration,
        article_2_3_land=constraint_info.article_2_3_land,
        article_4=constraint_info.article_4,
        listed=constraint_info.listed,
    )

    # --- 3. Evaluate ---------------------------------------------------------
    result = evaluate(p)

    return CheckResponse(
        status=result.status,
        findings=[FindingOut(**f.__dict__) for f in result.findings],
        other_consents=[FindingOut(**f.__dict__) for f in result.other_consents],
        unknown_fields=sorted(result.unknown_fields),
        constraints=constraint_info,
    )
