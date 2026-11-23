"""Score the router and extractor agents against eval/gold_facts.csv.

Run:
    python eval/eval_agents.py                 # calls Ollama (first run), then cached
    python eval/eval_agents.py --offline       # cache only, no model needed
    python eval/eval_agents.py --model llama3.2:3b
    python eval/eval_agents.py --baseline      # keyword rules, no LLM (comparison)

What is measured
----------------
1. Householder detection   - does the router spot schools / warehouses?
2. Work-type routing       - per work type precision / recall / F1 (set match per case)
3. Extension facts         - position and storeys, compared as multisets per case
4. Cladding flag           - accuracy
5. Grounding               - % of quoted evidence that does not appear in the text (hallucination)
6. Pipeline status vs real outcome (householder cases) - reported, not yet the headline:
   Class B-G rules arrive on Day 6, so most items still go to officer review.

LLM answers are cached in eval/llm_cache/ (committed), so anyone can reproduce
these numbers with --offline and no model installed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdcheck.agents.baseline import KeywordClient  # noqa: E402
from pdcheck.agents.pipeline import run_pipeline  # noqa: E402
from pdcheck.agents.schemas import WORK_TYPES  # noqa: E402
from pdcheck.llm.client import LLMUnavailable, OllamaClient  # noqa: E402

EVAL = Path(__file__).resolve().parent
CACHE_DIR = EVAL / "llm_cache"
RESULTS_DIR = EVAL / "results"


def _load() -> list[dict]:
    cases = {r["case_id"]: r for r in csv.DictReader(open(EVAL / "cases.csv", encoding="utf-8"))}
    gold = {r["case_id"]: r for r in csv.DictReader(open(EVAL / "gold_facts.csv", encoding="utf-8"))}
    missing = set(cases) ^ set(gold)
    if missing:
        raise SystemExit(f"cases.csv and gold_facts.csv disagree on case ids: {sorted(missing)}")
    return [{**cases[cid], "gold": gold[cid]} for cid in cases]


def _gold_extensions(s: str) -> Counter:
    return Counter(x for x in s.split(";") if x)


def _pred_extensions(facts: dict) -> Counter:
    out = Counter()
    for e in facts.get("extensions", []):
        out[f"{e['position']}:{e['storeys'] if e['storeys'] is not None else '?'}"] += 1
    return out


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="Ollama model tag (default: PDCHECK_LLM_MODEL or qwen3:4b)")
    ap.add_argument("--offline", action="store_true", help="Use cached answers only")
    ap.add_argument("--limit", type=int, default=None, help="Only run the first N cases (smoke test)")
    ap.add_argument("--baseline", action="store_true", help="Use keyword rules instead of an LLM")
    args = ap.parse_args()

    client = KeywordClient() if args.baseline else OllamaClient(
        model=args.model, cache_dir=CACHE_DIR, offline=args.offline or None)
    rows = _load()[: args.limit]
    print(f"Model: {client.model}   cases: {len(rows)}\n")

    per_case = []
    t0 = time.perf_counter()
    for i, row in enumerate(rows, 1):
        try:
            res = run_pipeline(row["proposal_text"], client)
        except LLMUnavailable as exc:
            raise SystemExit(f"\n{exc}")
        fresh = sum(1 for s in res.trace if not s.cached)
        print(f"[{i:>2}/{len(rows)}] {row['case_id']}  {res.status:<24} "
              f"{'cached' if fresh == 0 else f'{res.total_ms / 1000:.1f}s'}")
        per_case.append((row, res))
    elapsed = time.perf_counter() - t0

    # ---- 1. householder detection ---------------------------------------------
    hh_correct = sum(
        1 for row, res in per_case if (res.householder is not False) == (row["gold"]["householder"] == "true")
    )

    # ---- 2. routing -----------------------------------------------------------
    counts = {wt: Counter() for wt in WORK_TYPES}
    exact = 0
    for row, res in per_case:
        gold = set(row["gold"]["works"].split(";"))
        router = res.trace[0] if res.trace else None
        pred = {it["work_type"] for it in router.output["items"]} if router and router.ok else set()
        exact += gold == pred
        for wt in WORK_TYPES:
            if wt in gold and wt in pred:
                counts[wt]["tp"] += 1
            elif wt in pred:
                counts[wt]["fp"] += 1
            elif wt in gold:
                counts[wt]["fn"] += 1

    # ---- 3/4. extraction (householder cases where gold is householder) ---------
    hh_rows = [(row, res) for row, res in per_case if row["gold"]["householder"] == "true"]
    ext_exact = ext_total = clad_correct = 0
    for row, res in hh_rows:
        gold_ext = _gold_extensions(row["gold"]["extensions"])
        if gold_ext or res.facts.get("extensions"):
            ext_total += 1
            ext_exact += gold_ext == _pred_extensions(res.facts)
        clad_correct += bool(res.facts.get("cladding")) == (row["gold"]["cladding"] == "true")

    # ---- 5. grounding ---------------------------------------------------------
    checks = [c for _, res in per_case for s in res.trace for c in s.evidence_checks]
    ungrounded = [c.evidence for c in checks if not c.found]
    failed_steps = [(row["case_id"], s.agent, s.error) for row, res in per_case for s in res.trace if not s.ok]

    # ---- 6. status vs outcome -------------------------------------------------
    status_by_outcome = Counter((row["real_outcome"], res.status) for row, res in hh_rows)

    # ---- report ---------------------------------------------------------------
    n = len(per_case)
    print(f"\n{'=' * 64}\nAGENT EVAL  model={client.model}  cases={n}  time={elapsed:.0f}s\n{'=' * 64}")
    print(f"Householder detection     {hh_correct}/{n}  ({hh_correct / n:.0%})")
    print(f"Work types exact match    {exact}/{n}  ({exact / n:.0%})")
    print(f"Extension facts exact     {ext_exact}/{ext_total}  ({ext_exact / max(ext_total, 1):.0%})")
    print(f"Cladding flag             {clad_correct}/{len(hh_rows)}  ({clad_correct / max(len(hh_rows), 1):.0%})")
    print(f"Ungrounded evidence       {len(ungrounded)}/{len(checks)} quotes not found in text")
    print(f"Failed agent steps        {len(failed_steps)}")
    print("\nRouting per work type        P      R      F1   (support)")
    routing = {}
    for wt in WORK_TYPES:
        c = counts[wt]
        support = c["tp"] + c["fn"]
        if support == 0 and c["fp"] == 0:
            continue
        p, r, f = _prf(c["tp"], c["fp"], c["fn"])
        routing[wt] = {"precision": p, "recall": r, "f1": f, "support": support, **c}
        print(f"  {wt:<22} {p:>6.0%} {r:>6.0%} {f:>6.2f}   ({support})")
    print("\nPipeline status by real outcome (householder cases):")
    for (outcome, status), k in sorted(status_by_outcome.items()):
        print(f"  real={outcome:<11} status={status:<24} n={k}")
    if ungrounded:
        print("\nUngrounded evidence (first 10):")
        for e in ungrounded[:10]:
            print(f"  - {e!r}")
    if failed_steps:
        print("\nFailed steps:")
        for cid, agent, err in failed_steps[:10]:
            print(f"  {cid} {agent}: {err}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"agents_{client.model.replace(':', '_').replace('/', '_')}.json"
    out.write_text(json.dumps({
        "model": client.model,
        "cases": n,
        "householder_accuracy": hh_correct / n,
        "works_exact_match": exact / n,
        "extension_exact": ext_exact / max(ext_total, 1),
        "cladding_accuracy": clad_correct / max(len(hh_rows), 1),
        "ungrounded_evidence": len(ungrounded),
        "evidence_checks": len(checks),
        "routing": routing,
        "status_by_outcome": {f"{o}|{s}": k for (o, s), k in status_by_outcome.items()},
        "per_case": [{"case_id": row["case_id"], "real_outcome": row["real_outcome"], **res.to_dict()}
                     for row, res in per_case],
    }, indent=2), encoding="utf-8")
    print(f"\nFull results: {out}")


if __name__ == "__main__":
    main()
