"""Deterministic rule engine for householder permitted development (Class A).

Thresholds and blockers are decided in code. Interpretive rules are not decided here:
they are returned as `needs_review` so an LLM layer (or a human) can look at them with citations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"

OUTCOME_ORDER = ["needs_permission", "prior_approval_possible", "needs_review"]


@dataclass
class Proposal:
    """Facts about a proposed householder extension. Unknown values stay None."""

    dwelling_type: str | None = None  # detached | semi | terraced | flat
    extension_position: str | None = None  # rear | side | front
    storeys: int | None = None
    height_m: float | None = None
    eaves_height_m: float | None = None
    rear_depth_m: float | None = None
    distance_to_boundary_m: float | None = None
    side_width_ratio: float | None = None  # extension width / width of original house
    curtilage_cover_ratio: float | None = None
    exceeds_highest_roof: bool | None = None
    exceeds_existing_eaves: bool | None = None
    beyond_principal_elevation: bool | None = None
    cladding: bool | None = None
    # multi-storey rear
    distance_to_rear_boundary_m: float | None = None  # for A.1(h)(ii) 7m rule
    # additional blockers (A.1(a), A.1(l), A.1(k))
    permitted_use_only: bool | None = None             # use granted only via Part 3 change-of-use
    built_under_part_20: bool | None = None            # house built under Part 20 PD right
    includes_verandah_balcony_platform: bool | None = None  # A.1(k)(i)
    includes_chimney_flue: bool | None = None               # A.1(k)(iii)
    includes_roof_alteration: bool | None = None            # A.1(k)(iv)
    # constraints (filled from constraint lookups)
    article_2_3_land: bool | None = None
    article_4: bool | None = None
    listed: bool | None = None


@dataclass
class Finding:
    rule_id: str
    outcome: str
    description: str
    citation: str
    verify: bool


@dataclass
class Result:
    status: str  # needs_permission | prior_approval_possible | needs_review | likely_permitted
    findings: list[Finding] = field(default_factory=list)
    other_consents: list[Finding] = field(default_factory=list)
    unknown_fields: set[str] = field(default_factory=set)


def load_rules(name: str = "class_a.yaml") -> list[dict[str, Any]]:
    with open(RULES_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["rules"]


def _matches(when: dict[str, Any], p: Proposal) -> bool:
    for key, expected in when.items():
        actual = getattr(p, key)
        if actual is None:
            return False
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _condition_true(cond: dict[str, Any], p: Proposal, unknown: set[str]) -> bool:
    actual = getattr(p, cond["field"])
    if actual is None:
        unknown.add(cond["field"])
        return False
    op, value = cond["op"], cond["value"]
    if op == "gt":
        return actual > value
    if op == "lt":
        return actual < value
    if op == "eq":
        return actual == value
    raise ValueError(f"unknown op {op!r}")


def evaluate(p: Proposal, rules: list[dict[str, Any]] | None = None) -> Result:
    rules = rules if rules is not None else load_rules()
    result = Result(status="likely_permitted")
    for rule in rules:
        if not _matches(rule.get("when", {}), p):
            continue
        finding = Finding(
            rule_id=rule["id"],
            outcome=rule["outcome"],
            description=rule["description"],
            citation=rule["citation"],
            verify=rule.get("verify", True),
        )
        if rule["kind"] == "interpretive":
            result.findings.append(finding)
            continue
        conds = rule.get("fails_if", [])
        if conds and all(_condition_true(c, p, result.unknown_fields) for c in conds):
            if rule["outcome"] == "other_consent_required":
                result.other_consents.append(finding)
            else:
                result.findings.append(finding)

    outcomes = {f.outcome for f in result.findings}
    # A hard "needs permission" wins over the prior-approval route.
    for status in OUTCOME_ORDER:
        if status in outcomes:
            result.status = status
            break
    return result
