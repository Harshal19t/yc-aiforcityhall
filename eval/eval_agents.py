"""Score the router and extractor agents against gold facts.

Run:
    python eval/eval_agents.py                       # Sheffield set, local LLM (cached after first run)
    python eval/eval_agents.py --set messy           # synthetic homeowner-style descriptions
    python eval/eval_agents.py --set messy --baseline
    python eval/eval_agents.py --set messy --model qwen3.5:4b
    python eval/eval_agents.py --offline             # cached answers only, no model needed

Two test sets
-------------
council  The 48 Sheffield LDC descriptions (formulaic council wording). Gold: eval/gold_facts.csv.
messy    40 homeowner-style descriptions written by Claude (SYNTHETIC; includes negation, synonyms,
         units, internal-only works). Gold: eval/messy_cases.csv. Add your own rows with a different
         `author` value; they are scored the same way.

Metrics
-------
1. Householder detection        router spots non-houses
2. Work types exact match       set of work types per case, plus per-type precision/recall
3. Extension facts exact        position + storeys, per case
4. Dwelling type / depth / height / cladding accuracy  (where the gold set has them)
5. Grounding                    quoted evidence or numbers not present in the text
6. Verdict agreement            pipeline verdict from raw text vs the verdict the SAME pipeline gives when
                                handed the gold facts. This is the end-to-end test: it measures how much
                                of the final answer survives extraction errors, independent of council outcomes.
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
from pdcheck.agents.prompts import strip_boilerplate  # noqa: E402
from pdcheck.agents.schemas import WORK_TYPES  # noqa: E402
from pdcheck.llm.client import LLMResponse, LLMUnavailable, OllamaClient  # noqa: E402

EVAL = Path(__file__).resolve().parent
CACHE_DIR = EVAL / "llm_cache"
RESULTS_DIR = EVAL / "results"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _opt_float(v: str | None) -> float | None:
    return float(v) if v not in (None, "") else None


def _norm_gold(g: dict, has_dims: bool) -> dict:
    return {
        "householder": g["householder"] == "true",
        "works": {w for w in g["works"].split(";") if w},
        "extensions": Counter(x for x in g["extensions"].split(";") if x),
        "cladding": g["cladding"] == "true",
        "has_dims": has_dims,
        "dwelling_type": (g.get("dwelling_type") or None) if has_dims else None,
        "rear_depth_m": _opt_float(g.get("rear_depth_m")) if has_dims else None,
        "height_m": _opt_float(g.get("height_m")) if has_dims else None,
    }


def load_set(name: str) -> list[dict]:
    if name == "council":
        cases = {r["case_id"]: r for r in csv.DictReader(open(EVAL / "cases.csv", encoding="utf-8"))}
        gold = {r["case_id"]: r for r in csv.DictReader(open(EVAL / "gold_facts.csv", encoding="utf-8"))}
        missing = set(cases) ^ set(gold)
        if missing:
            raise SystemExit(f"cases.csv and gold_facts.csv disagree on case ids: {sorted(missing)}")
        return [{"case_id": cid, "text": cases[cid]["proposal_text"], "outcome": cases[cid]["real_outcome"],
                 "gold": _norm_gold(gold[cid], has_dims=False)} for cid in cases]
    rows = list(csv.DictReader(open(EVAL / "messy_cases.csv", encoding="utf-8")))
    return [{"case_id": r["case_id"], "text": r["text"], "outcome": None,
             "gold": _norm_gold(r, has_dims=True)} for r in rows]


# ---------------------------------------------------------------------------
# Oracle: a "client" that answers with the gold facts
# ---------------------------------------------------------------------------

class GoldClient:
    model = "gold-oracle"

    def __init__(self, rows: list[dict]) -> None:
        self.by_text = {strip_boilerplate(r["text"]): r["gold"] for r in rows}

    def complete_json(self, system: str, user: str, schema: dict) -> LLMResponse:
        text = user.split('Description: "', 1)[-1].rsplit('"', 1)[0]
        g = self.by_text[text]
        if "classify" in system:
            if not g["householder"]:
                items = [{"work_type": "non_householder", "evidence": ""}]
            else:
                items = [{"work_type": w, "evidence": ""} for w in sorted(g["works"])]
            data = {"householder": g["householder"], "items": items}
        else:
            exts = []
            for key, n in g["extensions"].items():
                pos, st = key.split(":")
                exts.extend([{"position": pos, "storeys": None if st == "?" else int(st), "evidence": ""}] * n)
            data = {"extensions": exts, "dwelling_type": g["dwelling_type"], "cladding": g["cladding"],
                    "cladding_evidence": None, "rear_depth_m": g["rear_depth_m"], "height_m": g["height_m"]}
        return LLMResponse(data=data, model=self.model, cached=True, latency_ms=0)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _pred_extensions(facts: dict) -> Counter:
    out: Counter = Counter()
    for e in facts.get("extensions", []):
        out[f"{e['position']}:{e['storeys'] if e['storeys'] is not None else '?'}"] += 1
    return out


def _pred_works(res) -> set[str]:
    router = res.trace[0] if res.trace else None
    return {i["work_type"] for i in router.output["items"]} if router and router.ok and router.output else set()


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def _close(a: float | None, b: float | None) -> bool:
    return a is None and b is None or (a is not None and b is not None and abs(a - b) < 1e-9)


def _pct(k: int, n: int) -> str:
    return f"{k}/{n}  ({k / n:.0%})" if n else "n/a"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["council", "messy"], default="council")
    ap.add_argument("--model", default=None, help="Ollama model tag (default: PDCHECK_LLM_MODEL or qwen3:4b)")
    ap.add_argument("--offline", action="store_true", help="Use cached answers only")
    ap.add_argument("--limit", type=int, default=None, help="Only run the first N cases (smoke test)")
    ap.add_argument("--baseline", action="store_true", help="Use keyword rules instead of an LLM")
    ap.add_argument("--oracle", action="store_true", help="Feed the gold facts (sanity check, should score 100%%)")
    args = ap.parse_args()

    rows = load_set(args.set)[: args.limit]
    oracle = GoldClient(load_set(args.set))
    if args.oracle:
        client = oracle
    elif args.baseline:
        client = KeywordClient()
    else:
        client = OllamaClient(model=args.model, cache_dir=CACHE_DIR, offline=args.offline or None)
    print(f"Set: {args.set}   Model: {client.model}   cases: {len(rows)}\n")

    per_case = []
    t0 = time.perf_counter()
    for i, row in enumerate(rows, 1):
        try:
            res = run_pipeline(row["text"], client)
        except LLMUnavailable as exc:
            raise SystemExit(f"\n{exc}")
        gold_res = run_pipeline(row["text"], oracle)
        fresh = sum(1 for s in res.trace if not s.cached)
        print(f"[{i:>2}/{len(rows)}] {row['case_id']}  {res.status:<24} "
              f"{'cached' if fresh == 0 else f'{res.total_ms / 1000:.1f}s'}")
        per_case.append((row, res, gold_res))
    elapsed = time.perf_counter() - t0
    n = len(per_case)

    # 1. householder detection
    hh_ok = sum(1 for r, res, _ in per_case if (res.householder is not False) == r["gold"]["householder"])

    # 2. routing
    counts = {wt: Counter() for wt in WORK_TYPES}
    works_ok = 0
    works_errors = []
    for r, res, _ in per_case:
        gold, pred = r["gold"]["works"] or set(), _pred_works(res)
        if not r["gold"]["householder"]:
            gold = {"non_householder"}
        if r["gold"]["householder"] and not res.householder is False:
            pred = pred - {"non_householder"}
        works_ok += gold == pred
        if gold != pred:
            works_errors.append((r["case_id"], r["text"], gold, pred))
        for wt in WORK_TYPES:
            if wt in gold and wt in pred:
                counts[wt]["tp"] += 1
            elif wt in pred:
                counts[wt]["fp"] += 1
            elif wt in gold:
                counts[wt]["fn"] += 1

    # 3-4. extraction facts (householder cases only)
    hh = [(r, res, g) for r, res, g in per_case if r["gold"]["householder"]]
    ext_ok = ext_n = clad_ok = dw_ok = dp_ok = ht_ok = 0
    fact_errors = []
    for r, res, _ in hh:
        g = r["gold"]
        f = res.facts or {}
        if g["extensions"] or f.get("extensions"):
            ext_n += 1
            good = g["extensions"] == _pred_extensions(f)
            ext_ok += good
            if not good:
                fact_errors.append((r["case_id"], "extensions", dict(g["extensions"]), dict(_pred_extensions(f))))
        clad_ok += bool(f.get("cladding")) == g["cladding"]
        if g["has_dims"]:
            dw_ok += f.get("dwelling_type") == g["dwelling_type"]
            dp_ok += _close(f.get("rear_depth_m"), g["rear_depth_m"])
            ht_ok += _close(f.get("height_m"), g["height_m"])
            for fld, ok in (("dwelling_type", f.get("dwelling_type") == g["dwelling_type"]),
                            ("rear_depth_m", _close(f.get("rear_depth_m"), g["rear_depth_m"])),
                            ("height_m", _close(f.get("height_m"), g["height_m"]))):
                if not ok:
                    fact_errors.append((r["case_id"], fld, g[fld], f.get(fld)))

    # 5. grounding
    checks = [c for _, res, _ in per_case for s in res.trace for c in s.evidence_checks]
    ungrounded = [c.evidence for c in checks if not c.found]
    failed = [(r["case_id"], s.agent, s.error) for r, res, _ in per_case for s in res.trace if not s.ok]

    # 6. verdict agreement
    agree = sum(1 for _, res, g in per_case if res.status == g.status)
    verdict_by_gold: dict[str, Counter] = {}
    for _, res, g in per_case:
        verdict_by_gold.setdefault(g.status, Counter())[res.status] += 1
    verdict_errors = [(r["case_id"], g.status, res.status) for r, res, g in per_case if res.status != g.status]
    # Most gold verdicts are just needs_review (any system matches those). Report the informative ones separately.
    informative = [(res, g) for _, res, g in per_case if g.status != "needs_review"]
    informative_ok = sum(1 for res, g in informative if res.status == g.status)

    # ---- report ----------------------------------------------------------------
    print(f"\n{'=' * 66}\nAGENT EVAL  set={args.set}  model={client.model}  cases={n}  time={elapsed:.0f}s\n{'=' * 66}")
    print(f"Householder detection     {_pct(hh_ok, n)}")
    print(f"Work types exact match    {_pct(works_ok, n)}")
    print(f"Extension facts exact     {_pct(ext_ok, ext_n)}")
    print(f"Cladding flag             {_pct(clad_ok, len(hh))}")
    if hh and hh[0][0]["gold"]["has_dims"]:
        print(f"Dwelling type             {_pct(dw_ok, len(hh))}")
        print(f"Rear depth (m)            {_pct(dp_ok, len(hh))}")
        print(f"Height (m)                {_pct(ht_ok, len(hh))}")
    print(f"Ungrounded evidence       {len(ungrounded)}/{len(checks)} quotes or numbers not found in text")
    print(f"Failed agent steps        {len(failed)}")
    print(f"VERDICT AGREEMENT         {_pct(agree, n)}   (verdict from raw text vs verdict from gold facts)")
    print(f"  ...informative only     {_pct(informative_ok, len(informative))}   "
          f"(gold verdict is not needs_review; the cases that matter)")

    print("\nRouting per work type        P      R      F1   (support)")
    routing = {}
    for wt in WORK_TYPES:
        c = counts[wt]
        support = c["tp"] + c["fn"]
        if support == 0 and c["fp"] == 0:
            continue
        p, rc, f1 = _prf(c["tp"], c["fp"], c["fn"])
        routing[wt] = {"precision": p, "recall": rc, "f1": f1, "support": support, **c}
        print(f"  {wt:<22} {p:>6.0%} {rc:>6.0%} {f1:>6.2f}   ({support})")

    print("\nVerdict from gold facts -> verdict from raw text:")
    for gold_status, c in sorted(verdict_by_gold.items()):
        print(f"  gold={gold_status:<24} " + "  ".join(f"{s}:{k}" for s, k in sorted(c.items())))

    if args.set == "council":
        by_outcome = Counter((r["outcome"], res.status) for r, res, _ in hh)
        print("\nPipeline status by real council outcome (householder cases):")
        for (o, s), k in sorted(by_outcome.items()):
            print(f"  real={o:<11} status={s:<24} n={k}")

    for title, items in (("Work-type errors", works_errors[:12]), ("Fact errors", fact_errors[:15]),
                         ("Verdict disagreements", verdict_errors[:12])):
        if items:
            print(f"\n{title} (first {len(items)}):")
            for it in items:
                print("  " + " | ".join(str(x)[:70] for x in it))
    if ungrounded:
        print("\nUngrounded (first 10): " + "; ".join(repr(e) for e in ungrounded[:10]))
    if failed:
        print("\nFailed steps:")
        for cid, agent, err in failed[:10]:
            print(f"  {cid} {agent}: {err}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"agents_{args.set}_{client.model.replace(':', '_').replace('/', '_')}.json"
    out.write_text(json.dumps({
        "set": args.set, "model": client.model, "cases": n,
        "householder_accuracy": hh_ok / n, "works_exact_match": works_ok / n,
        "extension_exact": ext_ok / max(ext_n, 1), "cladding_accuracy": clad_ok / max(len(hh), 1),
        "dwelling_accuracy": dw_ok / max(len(hh), 1), "depth_accuracy": dp_ok / max(len(hh), 1),
        "height_accuracy": ht_ok / max(len(hh), 1),
        "ungrounded": len(ungrounded), "evidence_checks": len(checks),
        "verdict_agreement": agree / n,
        "verdict_agreement_informative": informative_ok / max(len(informative), 1),
        "informative_cases": len(informative), "routing": routing,
        "per_case": [{"case_id": r["case_id"], "gold_status": g.status, **res.to_dict()} for r, res, g in per_case],
    }, indent=2, default=list), encoding="utf-8")
    print(f"\nFull results: {out}")


if __name__ == "__main__":
    main()
