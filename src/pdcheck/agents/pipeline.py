"""Orchestrator: description text -> routed works -> extracted facts -> rule engine.

    description ─► scope_router (LLM) ─► fact_extractor (LLM) ─► rule engine (deterministic)
                                                                  per work item
                                     └────────────── trace of every step ─────────────┘

The LLMs only turn text into structured facts. Every lawful / not-lawful
judgement comes from the deterministic engine or is returned as needs_review
for an officer. The model is never asked "is this permitted development?".
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from pdcheck.agents.agents import AgentStep, run_extractor, run_router
from pdcheck.agents.prompts import strip_boilerplate
from pdcheck.agents.schemas import ExtensionFacts, ExtractorOutput, RouterOutput
from pdcheck.check.engine import Finding, Proposal, evaluate
from pdcheck.llm.client import LLMClient

STATUS_ORDER = ["needs_permission", "prior_approval_possible", "needs_review", "likely_permitted"]

# Work types the Class A engine can assess today.
ENGINE_WORK_TYPES = {"extension", "external_alteration"}

# Work types with no encoded rules yet: (citation, what an officer must check).
PENDING_RULES: dict[str, tuple[str, str]] = {
    "roof_enlargement": (
        "GPDO 2015 Sch 2 Pt 1 Class B",
        "Dormer / hip-to-gable falls under Class B, not Class A. Check the 40 m³ (terraced) / 50 m³ (other) "
        "volume limit, that nothing faces a highway on the principal elevation, and that it is no higher than the ridge.",
    ),
    "roof_other": (
        "GPDO 2015 Sch 2 Pt 1 Class C",
        "Rooflights and other roof alterations fall under Class C. Check projection (max 0.15 m), height "
        "and obscure-glazing of side-facing windows.",
    ),
    "porch": ("GPDO 2015 Sch 2 Pt 1 Class D", "Check porch footprint (max 3 m²), height (max 3 m) and 2 m from a highway boundary."),
    "outbuilding": (
        "GPDO 2015 Sch 2 Pt 1 Class E",
        "Check the building is incidental to the house, not forward of the principal elevation, height limits "
        "(2.5 m within 2 m of a boundary) and 50% curtilage cover.",
    ),
    "chimney_flue": ("GPDO 2015 Sch 2 Pt 1 Class G", "Check the flue is no more than 1 m above the highest part of the roof."),
    "solar": ("GPDO 2015 Sch 2 Pt 14 Class A", "Check panels project no more than 0.2 m and are not above the ridge."),
    "demolition": ("GPDO 2015 Sch 2 Pt 11 Class B", "Usually minor; check whether prior approval applies."),
    "caravan": (
        "Town and Country Planning Act 1990 s.55",
        "Siting a mobile home is not householder PD. It is lawful only if the use is genuinely ancillary to the "
        "house, which is a question of fact and degree for the officer.",
    ),
}


@dataclass
class ItemAssessment:
    work_type: str
    evidence: str
    status: str
    findings: list[dict[str, Any]]
    note: str = ""


@dataclass
class PipelineResult:
    status: str  # out_of_scope | error | needs_permission | prior_approval_possible | needs_review | likely_permitted
    householder: bool | None
    description: str
    items: list[ItemAssessment] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    trace: list[AgentStep] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    error: str | None = None
    total_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trace"] = [s.to_dict() for s in self.trace]
        return d


def _worst(statuses: list[str]) -> str:
    for s in STATUS_ORDER:
        if s in statuses:
            return s
    return "likely_permitted"


def _finding_dict(f: Finding) -> dict[str, Any]:
    return asdict(f)


def _engine_item(
    work_type: str,
    evidence: str,
    base_fields: dict[str, Any],
    positions: list[str | None],
    storeys: int | None,
    unknown: set[str],
) -> ItemAssessment:
    findings: dict[str, Finding] = {}
    statuses = []
    for pos in positions:
        p = Proposal(**{**base_fields, "extension_position": pos, "storeys": storeys})
        r = evaluate(p)
        statuses.append(r.status)
        unknown |= r.unknown_fields
        for f in r.findings + r.other_consents:
            findings.setdefault(f.rule_id, f)
    return ItemAssessment(
        work_type=work_type,
        evidence=evidence,
        status=_worst(statuses),
        findings=[_finding_dict(f) for f in findings.values()],
    )


def run_pipeline(
    description: str,
    client: LLMClient,
    known: dict[str, Any] | None = None,
) -> PipelineResult:
    """Run the full pipeline.

    `known` holds Proposal fields the user has confirmed (form inputs, constraint
    lookup). They override anything the extractor produced.
    """
    start = time.perf_counter()
    text = strip_boilerplate(description)
    known = {k: v for k, v in (known or {}).items() if v is not None}
    result = PipelineResult(status="needs_review", householder=None, description=text)

    # 1. Route -----------------------------------------------------------------
    routed, step = run_router(client, text)
    result.trace.append(step)
    if routed is None:
        result.status, result.error = "error", f"router failed: {step.error}"
        return _finish(result, start)
    assert isinstance(routed, RouterOutput)
    result.householder = routed.householder
    only_non_hh = bool(routed.items) and all(i.work_type == "non_householder" for i in routed.items)
    if not routed.householder or only_non_hh:
        result.status = "out_of_scope"
        result.items = [ItemAssessment("non_householder", i.evidence, "out_of_scope", [],
                                       "Not a householder application: Part 1 permitted development does not apply.")
                        for i in routed.items]
        return _finish(result, start)

    # 2. Extract ---------------------------------------------------------------
    facts, step = run_extractor(client, text)
    result.trace.append(step)
    if facts is None:
        facts = ExtractorOutput(extensions=[], dwelling_type=None, cladding=False, rear_depth_m=None, height_m=None)
    result.facts = facts.model_dump()

    base: dict[str, Any] = {
        "dwelling_type": facts.dwelling_type,
        "rear_depth_m": facts.rear_depth_m,
        "height_m": facts.height_m,
        "cladding": facts.cladding,
    }
    base.update({k: v for k, v in known.items() if k not in ("extension_position", "storeys")})
    unknown: set[str] = set()

    # 3. Assess each work item ---------------------------------------------------
    work_types = [i.work_type for i in routed.items]
    for item in routed.items:
        wt = item.work_type
        if wt == "extension":
            continue  # handled below from the extractor's per-extension facts
        if wt == "external_alteration":
            result.items.append(_engine_item(wt, item.evidence, base, [None], None, unknown))
        elif wt in PENDING_RULES:
            citation, check = PENDING_RULES[wt]
            result.items.append(ItemAssessment(
                work_type=wt, evidence=item.evidence, status="needs_review",
                findings=[{"rule_id": f"{wt}_pending", "outcome": "needs_review", "description": check,
                           "citation": citation, "verify": True}],
                note="No encoded rules for this class yet: routed to officer review.",
            ))

    extensions = facts.extensions
    if "extension" in work_types and not extensions:
        # Router saw an extension but the extractor gave no detail: assess with unknowns.
        extensions = [ExtensionFacts(position="unspecified", storeys=None, evidence="")]
    for ext in extensions:
        pos = known.get("extension_position") or ext.position
        positions: list[str | None] = {"side_rear": ["side", "rear"], "unspecified": [None]}.get(pos, [pos])
        storeys = known.get("storeys") or ext.storeys
        result.items.append(_engine_item("extension", ext.evidence, base, positions, storeys, unknown))

    result.unknown_fields = sorted(unknown)
    result.status = _worst([i.status for i in result.items]) if result.items else "needs_review"
    return _finish(result, start)


def _finish(result: PipelineResult, start: float) -> PipelineResult:
    result.total_ms = int((time.perf_counter() - start) * 1000)
    return result
