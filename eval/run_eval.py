"""Run the rule engine over eval/cases.csv (form fields only) and print a confusion matrix.

Only householder cases are scored (non-householder sites are listed in eval/gold_facts.csv).
This script feeds the engine whatever structured fields are in cases.csv. Those fields are
blank for scraped cases, so this measures the engine with no extraction at all. The agent
pipeline (eval/eval_agents.py) is the main eval.

real_outcome should be one of: lawful | not_lawful | withdrawn
  withdrawn = applicant pulled the application; excluded from eval (no decision made).
Map the engine's status to a binary prediction:
  likely_permitted, needs_review (no hard failure) -> lawful
  needs_permission, prior_approval_possible        -> not_lawful
Decide and document this mapping before you tune anything, and report it in the write-up.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdcheck.check.engine import Proposal, evaluate  # noqa: E402

CASES = Path(__file__).with_name("cases.csv")


def _num(v: str):
    return float(v) if v not in ("", None) else None


def _bool(v: str):
    return {"true": True, "false": False}.get(v.strip().lower()) if v else None


def predict(row: dict) -> str:
    p = Proposal(
        dwelling_type=row.get("dwelling_type") or None,
        extension_position=row.get("extension_position") or None,
        storeys=int(row["storeys"]) if row.get("storeys") else None,
        rear_depth_m=_num(row.get("rear_depth_m", "")),
        height_m=_num(row.get("height_m", "")),
        article_2_3_land=_bool(row.get("article_2_3_land", "")),
        article_4=_bool(row.get("article_4", "")),
        listed=_bool(row.get("listed", "")),
    )
    status = evaluate(p).status
    return "not_lawful" if status in ("needs_permission", "prior_approval_possible") else "lawful"


def main() -> None:
    with open(CASES, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("No cases yet. Add rows to eval/cases.csv.")
        return
    # Exclude withdrawn and unlabelled rows — no decision was made
    gold_path = CASES.with_name("gold_facts.csv")
    non_hh = set()
    if gold_path.exists():
        with open(gold_path, newline="", encoding="utf-8") as fh:
            non_hh = {g["case_id"] for g in csv.DictReader(fh) if g["householder"] == "false"}
    scored = [r for r in rows if r["real_outcome"] in ("lawful", "not_lawful") and r["case_id"] not in non_hh]
    skipped = len(rows) - len(scored)
    if skipped:
        print(f"Skipping {skipped} row(s): withdrawn, blank outcome, or not a householder application")

    if not scored:
        print("No scoreable cases yet.")
        return

    predictions = [(r["real_outcome"], predict(r)) for r in scored]
    matrix = Counter(predictions)
    correct = sum(n for (real, pred), n in matrix.items() if real == pred)

    tp = matrix.get(("not_lawful", "not_lawful"), 0)
    fp = matrix.get(("lawful", "not_lawful"), 0)
    fn = matrix.get(("not_lawful", "lawful"), 0)
    tn = matrix.get(("lawful", "lawful"), 0)

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall    = tp / (tp + fn) if (tp + fn) else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print(f"cases: {len(scored)}  accuracy: {correct / len(scored):.1%}")
    print(f"not_lawful — precision: {precision:.1%}  recall: {recall:.1%}  F1: {f1:.2f}")
    print()
    print(f"  TP (correctly flagged)  : {tp}")
    print(f"  FP (false alarms)       : {fp}")
    print(f"  FN (missed refusals)    : {fn}")
    print(f"  TN (correctly cleared)  : {tn}")
    print()
    for (real, pred), n in sorted(matrix.items()):  # type: ignore[misc]
        mark = "✓" if real == pred else "✗"
        print(f"  {mark} real={real:<10} predicted={pred:<10} n={n}")

    # List any misses
    misses = [r for r in scored if r["real_outcome"] != predict(r)]
    if misses:
        print(f"\nMissed cases ({len(misses)}):")
        for r in misses:
            print(f"  {r['case_id']}  real={r['real_outcome']}  notes={r.get('notes','')[:70]}")


if __name__ == "__main__":
    main()
