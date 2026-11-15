"""Validate eval/cases.csv rows and show a quick summary.

Run: python eval/validate_cases.py

Checks:
  - Required columns are present
  - real_outcome is lawful | not_lawful
  - Numeric fields parse as floats
  - Boolean fields are true | false | blank
  - Flags rows where the engine has no inputs to decide (all numeric fields blank)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CASES = Path(__file__).with_name("cases.csv")

REQUIRED = [
    "case_id", "council", "proposal_text", "real_outcome",
    "dwelling_type", "extension_position",
]
NUMERIC = ["storeys", "rear_depth_m", "height_m"]
BOOLEANS = ["article_2_3_land", "article_4", "listed"]
VALID_OUTCOMES = {"lawful", "not_lawful"}
VALID_DWELLING = {"detached", "semi", "terraced", "flat", ""}
VALID_POSITION = {"rear", "side", "front", ""}


def _check_row(i: int, row: dict) -> list[str]:
    errors: list[str] = []
    for col in REQUIRED:
        if col not in row:
            errors.append(f"missing column '{col}'")
    if row.get("real_outcome", "").strip() not in VALID_OUTCOMES:
        errors.append(f"real_outcome must be lawful|not_lawful, got {row.get('real_outcome')!r}")
    if row.get("dwelling_type", "").strip() not in VALID_DWELLING:
        errors.append(f"dwelling_type must be detached|semi|terraced|flat|blank, got {row.get('dwelling_type')!r}")
    if row.get("extension_position", "").strip() not in VALID_POSITION:
        errors.append(f"extension_position must be rear|side|front|blank, got {row.get('extension_position')!r}")
    for col in NUMERIC:
        v = row.get(col, "").strip()
        if v:
            try:
                float(v)
            except ValueError:
                errors.append(f"{col} not a number: {v!r}")
    for col in BOOLEANS:
        v = row.get(col, "").strip().lower()
        if v not in ("true", "false", ""):
            errors.append(f"{col} must be true|false|blank, got {row.get(col)!r}")
    # Warn if no inputs that the engine uses
    has_input = any(row.get(c, "").strip() for c in NUMERIC + BOOLEANS + ["dwelling_type", "extension_position"])
    if not has_input:
        errors.append("WARN: no engine inputs — engine will return needs_review for every rule")
    return errors


def main() -> None:
    with open(CASES, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    total_errors = 0
    lawful = not_lawful = 0
    for i, row in enumerate(rows, start=2):  # row 1 is header
        errs = _check_row(i, row)
        if errs:
            for e in errs:
                prefix = "WARN" if e.startswith("WARN") else "ERR "
                print(f"row {i} ({row.get('case_id', '?')}): {prefix}: {e}")
                if not e.startswith("WARN"):
                    total_errors += 1
        if row.get("real_outcome") == "lawful":
            lawful += 1
        elif row.get("real_outcome") == "not_lawful":
            not_lawful += 1

    print(f"\n{len(rows)} cases  |  lawful={lawful}  not_lawful={not_lawful}  errors={total_errors}")
    if total_errors == 0:
        print("All rows valid.")


if __name__ == "__main__":
    main()
