"""Run the rule engine over eval/cases.csv and print a confusion matrix.

real_outcome should be one of: lawful | not_lawful (certificate granted / refused).
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
        dwelling_type=row["dwelling_type"] or None,
        extension_position=row["extension_position"] or None,
        storeys=int(row["storeys"]) if row["storeys"] else None,
        rear_depth_m=_num(row["rear_depth_m"]),
        height_m=_num(row["height_m"]),
        article_2_3_land=_bool(row["article_2_3_land"]),
        article_4=_bool(row["article_4"]),
        listed=_bool(row["listed"]),
    )
    status = evaluate(p).status
    return "not_lawful" if status in ("needs_permission", "prior_approval_possible") else "lawful"


def main() -> None:
    with open(CASES, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("No cases yet. Add rows to eval/cases.csv.")
        return
    matrix = Counter((r["real_outcome"], predict(r)) for r in rows)
    correct = sum(n for (real, pred), n in matrix.items() if real == pred)
    print(f"cases: {len(rows)}  accuracy: {correct / len(rows):.1%}")
    for (real, pred), n in sorted(matrix.items()):
        print(f"  real={real:<10} predicted={pred:<10} n={n}")


if __name__ == "__main__":
    main()
