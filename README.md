# pd-precheck

A pre-check for householder permitted development (PD) in England. Describe a proposed extension and an address, and the tool returns a cited assessment: what is likely fine, what likely needs permission or prior approval, and what needs a human to look at.

> Not planning advice. Permitted development has many edge cases. Always confirm with the local planning authority.

## Status

Early scaffold. Nothing here is evaluated yet.

## Approach

- **Deterministic first.** Thresholds (depths, heights, widths) and blockers (flats, Article 4, conservation areas) are plain code in `rules/` and `src/pdcheck/check/engine.py`.
- **LLM only where judgement is needed.** Extracting facts from a free-text proposal, and interpretive rules such as "materials of similar appearance".
- **Every finding cites its source.**
- **Unknowns are reported, never guessed.**

## Results

_To fill in after the evaluation (week 2)._

| Metric | Value |
|---|---|
| Cases | |
| Accuracy vs real outcome | |
| False "permitted" | |
| False "needs permission" | |

## Evaluation method

Ground truth: decided Certificate of Lawfulness (proposed development) applications from one council, where the council grants or refuses on the question of whether a proposal is permitted development. The case set is frozen before any tuning. See `eval/`.

## Data

All sources, licences and retrieval dates are in `data/SOURCES.md`. No drawings or personal data are stored in this repo.

## Run

```bash
pip install -e ".[dev]"
pytest
```

## Limits

_List honestly after the evaluation: edge cases the tool gets wrong, rules not yet encoded, councils not covered._
