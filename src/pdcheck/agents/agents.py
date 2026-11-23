"""The two LLM agents: scope router and fact extractor.

Each agent:
  1. sends one prompt with a JSON schema to the LLM client,
  2. validates the reply with Pydantic (one retry with the error message if it fails),
  3. checks every quoted `evidence` string really appears in the description,
  4. returns an AgentStep that the orchestrator stores in the trace.

An agent never raises on bad model output: it returns ok=False and the pipeline
treats its facts as unknown.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from pdcheck.agents.prompts import EXTRACTOR_SYSTEM, ROUTER_SYSTEM
from pdcheck.agents.schemas import ExtractorOutput, RouterOutput, llm_schema
from pdcheck.llm.client import LLMClient, LLMError, LLMUnavailable


@dataclass
class EvidenceCheck:
    evidence: str
    found: bool


@dataclass
class AgentStep:
    agent: str
    model: str
    ok: bool
    output: dict[str, Any] | None
    error: str | None = None
    cached: bool = False
    latency_ms: int = 0
    attempts: int = 0
    evidence_checks: list[EvidenceCheck] = field(default_factory=list)

    @property
    def hallucinated_evidence(self) -> list[str]:
        return [c.evidence for c in self.evidence_checks if not c.found]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hallucinated_evidence"] = self.hallucinated_evidence
        return d


# ---------------------------------------------------------------------------
# Evidence grounding
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = text.lower().replace("-", " ").replace("/", " ")
    text = re.sub(r"[^a-z0-9. ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def evidence_in_text(evidence: str | None, source: str) -> bool:
    """True if the quoted evidence appears in the source (ignoring case, punctuation, spacing)."""
    if not evidence:
        return True  # nothing claimed, nothing to check
    return _norm(evidence) in _norm(source)


# ---------------------------------------------------------------------------
# Generic structured call
# ---------------------------------------------------------------------------

def _run(
    agent: str,
    client: LLMClient,
    system: str,
    user: str,
    out_model: type[BaseModel],
    max_attempts: int = 2,
) -> tuple[BaseModel | None, AgentStep]:
    schema = llm_schema(out_model)
    step = AgentStep(agent=agent, model=client.model, ok=False, output=None)
    prompt = user
    for attempt in range(1, max_attempts + 1):
        step.attempts = attempt
        try:
            resp = client.complete_json(system, prompt, schema)
        except LLMUnavailable:
            raise  # infrastructure problem: surface it, do not hide it as "unknown"
        except LLMError as exc:
            step.error = str(exc)
            continue
        step.cached = resp.cached
        step.latency_ms += resp.latency_ms
        try:
            parsed = out_model.model_validate(resp.data)
        except ValidationError as exc:
            step.error = f"schema validation failed: {exc.errors()[:3]}"
            step.output = resp.data
            prompt = f"{user}\n\nYour previous answer was invalid ({exc.error_count()} errors). Answer again using the schema exactly."
            continue
        step.ok = True
        step.error = None
        step.output = parsed.model_dump()
        return parsed, step
    return None, step


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def run_router(client: LLMClient, description: str) -> tuple[RouterOutput | None, AgentStep]:
    parsed, step = _run("scope_router", client, ROUTER_SYSTEM, f'Description: "{description}"', RouterOutput)
    if parsed is not None:
        step.evidence_checks = [
            EvidenceCheck(item.evidence, evidence_in_text(item.evidence, description)) for item in parsed.items
        ]
    return parsed, step  # type: ignore[return-value]


def run_extractor(client: LLMClient, description: str) -> tuple[ExtractorOutput | None, AgentStep]:
    parsed, step = _run("fact_extractor", client, EXTRACTOR_SYSTEM, f'Description: "{description}"', ExtractorOutput)
    if parsed is not None:
        assert isinstance(parsed, ExtractorOutput)
        checks = [EvidenceCheck(e.evidence, evidence_in_text(e.evidence, description)) for e in parsed.extensions]
        if parsed.cladding_evidence:
            checks.append(EvidenceCheck(parsed.cladding_evidence, evidence_in_text(parsed.cladding_evidence, description)))
        step.evidence_checks = checks
        # Numbers must literally appear in the text; otherwise they are invented.
        for name in ("rear_depth_m", "height_m"):
            value = getattr(parsed, name)
            if value is not None and not _number_in_text(value, description):
                step.evidence_checks.append(EvidenceCheck(f"{name}={value}", False))
                setattr(parsed, name, None)
        step.output = parsed.model_dump()
    return parsed, step  # type: ignore[return-value]


def _number_in_text(value: float, text: str) -> bool:
    candidates = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text) for c in candidates)
