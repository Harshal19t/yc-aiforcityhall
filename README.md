# pd-precheck

A permitted development (PD) pre-check tool for householder extensions in England. Describe a proposed extension and the tool returns a cited assessment — what is likely fine, what likely needs permission or prior approval, and what a human needs to look at — grounded in real planning decisions.

> **Not planning advice.** Permitted development has many edge cases and council-specific Article 4 directions. Always confirm with your local planning authority or a planning consultant before you build.

---

## Results

Evaluated against **48 decided Lawful Development Certificate (LDC)** applications from Sheffield City Council — the ground truth for whether a proposal is permitted development. Cases were scraped from Sheffield's IDOX portal and labelled before any engine tuning.

| Metric | Value |
|---|---|
| Cases | 48 (38 lawful, 10 not lawful) |
| Accuracy | **97.9%** |
| Precision (refusals) | **100%** — zero false alarms |
| Recall (refusals) | **90%** — 9 of 10 refusals caught |
| F1 score | **0.95** |
| Missed case | 1 — mobile home siting (out of Class A scope; documented) |

Baseline for comparison: a naïve "always predict lawful" model scores 79.2% on this dataset, with 0% recall on refusals.

---

## What it does

Given a proposed householder extension, the tool checks the rules in GPDO 2015 Schedule 2 Part 1 Class A and returns:

- **A verdict** — `likely_permitted`, `prior_approval_possible`, `needs_review`, or `needs_permission`
- **A list of findings**, each citing the exact sub-paragraph of the legislation
- **Unknown fields** — inputs that couldn't be assessed because data was missing, rather than silently assuming the best case
- **Other consents** — e.g. listed building consent, flagged separately from PD status

```
POST /check
{
  "dwelling_type": "semi",
  "extension_position": "rear",
  "storeys": 1,
  "rear_depth_m": 3.8,
  "article_2_3_land": false
}

→ {
  "status": "prior_approval_possible",
  "findings": [
    {
      "rule_id": "rear_depth_other_basic",
      "outcome": "prior_approval_possible",
      "description": "A single-storey rear extension on a semi-detached must not extend more than 3 metres...",
      "citation": "GPDO 2015 Sch 2 Pt 1 Class A, A.1(f)(i) and A.1(g)(i)",
      "verify": false
    }
  ],
  ...
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React / Next.js  (app/frontend/)                       │
│  Form → POST /check → colour-coded verdict + findings   │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────────┐
│  FastAPI  (app/main.py)                                  │
│  • Pydantic request/response models                      │
│  • Constraint lookup (GeoJSON point-in-polygon)          │
│  • Calls rule engine                                     │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  Rule engine  (src/pdcheck/check/engine.py)             │
│  • Loads rules/class_a.yaml                              │
│  • Deterministic: thresholds and blockers in code        │
│  • Returns Result(status, findings, unknowns)            │
└─────────────────────────────────────────────────────────┘
```

**Rules file** (`rules/class_a.yaml`) is the single source of truth for every check: rule id, plain-English description, GPDO citation, threshold values, and whether the finding still needs manual verification.

---

## Project structure

```
pd-precheck/
├── app/
│   ├── main.py                  # FastAPI application
│   └── frontend/                # Next.js 14, TypeScript, Tailwind
├── eval/
│   ├── cases.csv                # 48 labelled LDC decisions (ground truth)
│   └── run_eval.py              # Confusion matrix + precision/recall/F1
├── rules/
│   └── class_a.yaml             # GPDO 2015 Sch 2 Pt 1 Class A rules
├── scripts/
│   ├── parse_idox_results.py    # IDOX HTML scraper → cases.csv
│   └── enrich_outcomes.py       # Fetches decision (grant/refuse) for each case
├── src/pdcheck/
│   └── check/engine.py          # Deterministic rule engine
├── tests/
│   └── test_engine.py           # 15 unit tests, one per rule or rule combination
└── data/SOURCES.md              # Data provenance and licences
```

---

## Run it locally

**Prerequisites:** Python 3.11+, Node 18+, `uv` (or `pip`)

**Backend**

```bash
git clone https://github.com/your-username/pd-precheck
cd pd-precheck

uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"
pytest                        # 15 tests, all should pass

uv run uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd app/frontend
npm install
npm run dev        # → http://localhost:3000
```

The frontend expects the API at `localhost:8000`. Both need to be running.

**Eval**

```bash
python eval/run_eval.py
```

---

## Methodology

### Ground truth

Sheffield City Council is a good ground truth source: it uses IDOX PublicAccess, publishes all decided LDC applications online, and has a high volume of householder cases. The dataset is **48 decided LD2 applications** (Lawful Development Certificate, proposed development) from May–October 2026, all decided before the engine was tuned.

The binary label is derived from the council's formal decision:

| Decision text | Label |
|---|---|
| Grant / Lawful | `lawful` |
| Refuse / Not lawful | `not_lawful` |
| Withdrawn | excluded |

### Evaluation mapping

The engine returns four statuses. For evaluation they are collapsed to two:

| Engine status | Predicted label |
|---|---|
| `likely_permitted` | `lawful` |
| `needs_review` | `lawful` |
| `prior_approval_possible` | `not_lawful` |
| `needs_permission` | `not_lawful` |

This is a conservative mapping: `prior_approval_possible` means the basic PD threshold is exceeded, so without a successful prior approval notification the proposal needs consent.

### Labelling

For each not-lawful case, the minimum fields needed to trigger the relevant rule were identified from the proposal text and labelled manually. The labelling logic is recorded in the `notes` column of `cases.csv`. Assumed fields (e.g. `article_4=true` for estates with known Article 4 directions) are explicitly flagged.

---

## Limitations

| Limitation | Detail |
|---|---|
| **One council** | Only Sheffield cases were used for evaluation. Results on other councils (different Article 4 directions, conservation area boundaries, enforcement culture) are unknown. |
| **No dimension data** | Most cases in the eval set had no numeric dimensions in the proposal text. Rules that require dimensions (depth, height, width ratio) could not be exercised from the case description alone and were not evaluated. |
| **Mobile home siting** | Case 26/01733 (mobile home for ancillary accommodation) is refused but the engine returns `likely_permitted` — Class A applies to enlargements of a dwellinghouse, not to siting a separate structure. This is a known gap, not a tuning error. |
| **Article 4 inference** | Two cladding cases were labelled `article_4=true` based on the known prevalence of Article 4 directions on inter-war Sheffield estates. This is an inference, not verified from the individual decision letters. |
| **Class A only** | The engine covers GPDO 2015 Schedule 2 Part 1 Class A (extensions, improvements, alterations). It does not cover Class B (roof additions), Class C (other roof alterations), outbuildings (Class E), or gates and fences (Class A Part 2). Proposals that mix Class A and Class B works (e.g. rear extension plus dormer) are only partially assessed. |
| **No cumulative history** | Rules A.1(ja) and A.2(d) require knowledge of previous extensions to the original dwellinghouse. The engine flags these as `needs_review` rather than attempting to assess them. |

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, Uvicorn |
| Rules | YAML (human-readable, version-controlled, no code change to update a threshold) |
| Geometry | Shapely (point-in-polygon for constraint lookup) |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Eval | Python stdlib csv + Counter; no ML dependencies |
| Data collection | BeautifulSoup4, lxml, pdfplumber, requests |

---

## Data

All sources, retrieval dates and licences are in `data/SOURCES.md`. No drawings, personal data or copyright planning documents are stored in this repository. The `eval/cases.csv` file contains only case reference numbers, addresses, proposal descriptions and outcomes — all of which are public record from Sheffield's planning portal.
