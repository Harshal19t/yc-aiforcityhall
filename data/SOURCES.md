# Data sources

Record every source here before you use it: what it is, who publishes it, the licence, and when you retrieved it.

| Source | Publisher | What it provides | Licence | Retrieved | Notes |
|---|---|---|---|---|---|
| Planning Data platform (planning.data.gov.uk) | MHCLG | Article 4 direction areas, conservation areas, listed building outlines and other designations | Open Government Licence v3.0 (confirm on the dataset page) | TODO | Coverage varies by council |
| GPDO 2015, Sch 2 Pt 1 | legislation.gov.uk | Text of the permitted development rules | TODO confirm | TODO | Use the current amended version, not "as made" |
| Householder PD technical guidance | GOV.UK | Plain-language guidance and diagrams for Class A to H | TODO confirm | TODO | |
| Chosen council: open datasets | TODO council | Article 4, conservation area, listed buildings, local plan | OGL (confirm per council) | TODO | |
| Chosen council: planning register | TODO council | Certificate of Lawfulness decisions (evaluation ground truth) | Check site terms | TODO | Check terms of use and robots rules BEFORE fetching. Do not store drawings. |

## Rules for this repo

- Keep raw downloads in `data/raw/` (gitignored). Keep only derived, non-personal data in `data/processed/`.
- Do not commit drawings or documents from council portals. Store extracted facts only.
- Do not store applicant names. Keep only what is needed for the case: proposal wording, constraints, outcome.
- Fetch slowly and prefer bulk downloads to scraping.
