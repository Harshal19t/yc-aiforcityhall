"""Run the agent pipeline on one description and print the trace.

    python scripts/try_agent.py "erection of single-storey rear extension and rear dormer"
    python scripts/try_agent.py --model llama3.2:3b "siting of a mobile home"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from pdcheck.agents.pipeline import run_pipeline  # noqa: E402
from pdcheck.llm.client import LLMUnavailable, OllamaClient  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("description")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    client = OllamaClient(model=args.model)
    print(f"Model: {client.model}\n")
    try:
        res = run_pipeline(args.description, client)
    except LLMUnavailable as exc:
        raise SystemExit(str(exc))

    for step in res.trace:
        flag = "ok" if step.ok else f"FAILED ({step.error})"
        timing = "cached" if step.cached else f"{step.latency_ms / 1000:.1f}s"
        print(f"── {step.agent}  [{flag}, {timing}]")
        print(json.dumps(step.output, indent=2))
        if step.hallucinated_evidence:
            print(f"   ! evidence not found in text: {step.hallucinated_evidence}")
        print()

    print(f"── verdict: {res.status}")
    for item in res.items:
        print(f"   {item.work_type:<20} {item.status:<24} \"{item.evidence}\"")
        for f in item.findings:
            if f["outcome"] != "needs_review" or f["rule_id"].endswith("_pending"):
                print(f"      - {f['rule_id']}: {f['citation']}")
    if res.unknown_fields:
        print(f"\n   unknown: {', '.join(res.unknown_fields)}")


if __name__ == "__main__":
    main()
