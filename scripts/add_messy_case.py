"""Add one hand-written test case to eval/messy_cases.csv by answering a few questions.

    uv run python scripts/add_messy_case.py

Write the description the way a normal homeowner would, NOT in council wording.
Label only what the text says (see docs/labelling_rubric.md). Never infer a house type or
a measurement that is not written down. Close the CSV in Excel first.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "eval" / "messy_cases.csv"
FIELDS = ["case_id", "author", "text", "householder", "works", "extensions",
          "dwelling_type", "rear_depth_m", "height_m", "cladding"]

WORKS = [
    ("extension", "extension to the house (rear or side)"),
    ("external_alteration", "windows/doors, render, insulation, cladding, garage conversion"),
    ("roof_enlargement", "dormer or hip-to-gable"),
    ("roof_other", "rooflights, re-roofing, new pitched roof over a structure"),
    ("porch", "porch"),
    ("outbuilding", "shed, garden room, garden office, summerhouse"),
    ("caravan", "mobile home or caravan"),
    ("chimney_flue", "chimney or flue"),
    ("solar", "solar panels"),
    ("demolition", "demolishing a store/outhouse/garage"),
]
POSITIONS = ["rear", "side", "side_rear", "front", "unspecified"]
DWELLINGS = ["detached", "semi", "terraced", "flat"]


def ask(prompt: str, valid: list[str] | None = None, allow_blank: bool = False) -> str:
    while True:
        v = input(prompt).strip()
        if not v and allow_blank:
            return ""
        if v and (valid is None or v in valid):
            return v
        print("  Not valid, try again." if v else "  Required.")


def ask_float(prompt: str) -> str:
    while True:
        v = input(prompt).strip()
        if not v:
            return ""
        try:
            float(v)
            return v
        except ValueError:
            print("  Enter a number in metres, or leave blank.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    author = os.environ.get("MESSY_AUTHOR") or ask("Your name (used as author, e.g. harshal): ")
    prefix = "U"
    existing = list(csv.DictReader(open(CSV_PATH, encoding="utf-8"))) if CSV_PATH.exists() else []
    n = sum(1 for r in existing if r["case_id"].startswith(prefix)) + 1
    case_id = f"{prefix}{n:02d}"

    print(f"\nCase {case_id}. Write the description in your own words.")
    text = ask("Description: ")
    householder = ask("Is it a normal house (not a shop, pub, school, office, flats)? [y/n]: ", ["y", "n"])
    works, extensions, dwelling, depth, height, cladding = "", "", "", "", "", "false"

    if householder == "n":
        works = "non_householder"
    else:
        print("\nWhich kinds of work does the text mention? (numbers, comma separated, blank = none)")
        for i, (k, d) in enumerate(WORKS, 1):
            print(f"  {i:>2}. {k:<20} {d}")
        picked: list[str] = []
        while True:
            raw = input("Choices: ").strip()
            try:
                picked = [WORKS[int(x) - 1][0] for x in raw.split(",") if x.strip()]
                break
            except (ValueError, IndexError):
                print("  Use the numbers above, e.g. 1,6")
        works = ";".join(picked)

        if "extension" in picked:
            print("\nOne line per extension. Position and storeys as the text says (storeys: 1, 2 or ? if not stated).")
            items = []
            while True:
                if items:
                    print(f"  Saved so far: {', '.join(items)}")
                    prompt = "  ANOTHER extension? Type its position, or just press Enter if there are no more: "
                else:
                    prompt = f"  Extension position {POSITIONS}: "
                pos = ask(prompt, POSITIONS, allow_blank=True)
                if not pos:
                    if items:
                        break
                    print("  Add at least one extension.")
                    continue
                st = ask("  How many floors? [1/2/? if not stated]: ", ["1", "2", "?"])
                items.append(f"{pos}:{st}")
            extensions = ";".join(items)

        dwelling = ask(f"\nHouse type if the text says {DWELLINGS} (blank = not stated): ", DWELLINGS, allow_blank=True)
        depth = ask_float("Extension depth in METRES if written in the text (blank = not stated; feet = blank): ")
        height = ask_float("Height in METRES if written in the text (blank = not stated): ")
        cladding = "true" if ask("Render, insulation or cladding on the walls? [y/n]: ", ["y", "n"]) == "y" else "false"

    row = [case_id, author, text, "true" if householder == "y" else "false", works, extensions,
           dwelling, depth, height, cladding]
    print("\nRow to add:\n  " + " | ".join(row))
    if ask("Save? [y/n]: ", ["y", "n"]) == "n":
        print("Discarded.")
        return
    try:
        new_file = not CSV_PATH.exists()
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(FIELDS)
            w.writerow(row)
    except PermissionError:
        raise SystemExit("Cannot write: close eval/messy_cases.csv in Excel and try again.")
    print(f"Saved as {case_id}. Run the script again for the next case.")


if __name__ == "__main__":
    main()
