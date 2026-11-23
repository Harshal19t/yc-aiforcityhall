# Labelling rubric for `eval/gold_facts.csv`

Gold facts are labelled **from the proposal description text only**. The same rules are applied to every case. The outcome column (`real_outcome` in `cases.csv`) is not used when labelling, and `gold_facts.csv` has no outcome column.

These labels are what the router and extractor agents are scored against. They describe *what the application says*, not whether it is lawful.

## Why this file exists

An earlier version of the eval set engine fields (`includes_roof_alteration`, `cladding`, `article_4`) only on cases that were refused. That leaks the answer into the input and inflates accuracy. This rubric replaces it: facts are labelled identically for lawful and refused cases.

Known limitation: the labeller had seen the outcomes before writing this rubric. The facts below are objective features of the text (does it mention a dormer? is it a school?), so there is little room for that to bias them, but it is recorded here for transparency.

## Columns

| Column | Values | Meaning |
|---|---|---|
| `case_id` | e.g. `26/02581/LD2` | Joins to `cases.csv` |
| `householder` | `true` / `false` | `false` if the site is not a dwellinghouse (school, warehouse, commercial or multi-unit building). Non-householder cases are excluded from scoring. |
| `works` | `;`-separated list of work types, see below | Every distinct type of work the description mentions |
| `extensions` | `;`-separated `position:storeys` items, e.g. `rear:1;side:1` | One item per extension mentioned. `position` is `rear`, `side`, `side_rear` or `unspecified`. `storeys` is `1`, `2` or `?` if not stated. Blank if there is no extension. |
| `cladding` | `true` / `false` | `true` if the description mentions render, external wall insulation, cladding, pebble dash, timber or tile hanging on the walls |

## Work types

| Work type | GPDO home | Include when the text mentions |
|---|---|---|
| `extension` | Part 1 Class A | Single or multi-storey extension to the house (rear, side) |
| `external_alteration` | Part 1 Class A | Changes to fenestration (windows/doors), repositioning windows, external wall insulation, render, cladding, converting a garage to habitable rooms |
| `roof_enlargement` | Part 1 Class B | Dormer (new or enlarged), hip-to-gable |
| `roof_other` | Part 1 Class C | Rooflights, re-roofing, replacement roof, forming a pitched roof over an existing structure |
| `porch` | Part 1 Class D | Erecting or altering a porch, including its roof |
| `outbuilding` | Part 1 Class E | Shed, garden room, garden office, detached outbuilding |
| `caravan` | Not Part 1 (use of land) | Siting a mobile home or caravan |
| `chimney_flue` | Part 1 Class G | Installing, altering or removing a chimney or flue |
| `solar` | Part 14 Class A | Solar panels |
| `demolition` | Part 11 | Demolishing an outbuilding, store, outhouse |
| `non_householder` | Out of scope | Use only when `householder` is `false` |

## Tie-break rules

1. "Loft conversion including rear dormer": label `roof_enlargement` only. The internal conversion is not development.
2. "Side/rear extension": one item, `side_rear`.
3. "Rear and side extensions": two items, `rear` and `side`.
4. A storey count is only recorded if the text says it ("single-storey", "two-storey"). Otherwise `?`.
5. Never infer dimensions, dwelling type or constraints. The text does not state them.

## Messy-text set (`eval/messy_cases.csv`)

40 synthetic homeowner-style descriptions written by Claude to test language understanding beyond formulaic council wording (negation, synonyms such as "back" for rear, units, internal-only works, non-householder uses). Labelled with this rubric before any model was run on it, and the prompts and baseline rules were frozen before the first run.

Extra columns: `dwelling_type` (only if the text names it), `rear_depth_m` and `height_m` (only if written in metres in the text; feet are left blank because the extractor is not asked to convert), and `author`.

Caveats: the cases are synthetic and were written by the same author as the prompts and baseline rules, so they are not independent. Add your own phrasings as new rows with `author` set to your name; they are scored identically.
