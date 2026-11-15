# Rule Verification Notes

Verified against: SI 2015/596 Schedule 2 Part 1 (current amended text from legislation.gov.uk)  
Source file uploaded by user: full current text of Part 1 Classes A–H  
Date verified: 2026-11-15

---

## Changes from draft YAML

### Rules removed
- None removed, but several were renamed for clarity.

### Rules added
1. **`change_of_use_exclusion`** (A.1(a)) — Class A does not apply where the dwelling's use as a dwellinghouse was granted only under Part 3 change-of-use classes (G, M, MA, N, P, PA, Q). The draft YAML did not have this as a separate rule.
2. **`part_20_exclusion`** (A.1(l)) — Class A does not apply to houses built under Part 20 (new dwellinghouses PD right). Added as a blocker.
3. **`no_verandah_balcony_raised_platform`** (A.1(k)(i)) — explicitly prohibits verandahs, balconies and raised platforms (>0.3m). Added as a threshold.
4. **`multi_storey_rear_depth_3m`** (A.1(h)(i)) — multi-storey rear extensions capped at 3m depth. Was missing from draft.
5. **`multi_storey_rear_7m_from_boundary`** (A.1(h)(ii)) — multi-storey rear extensions must not be within 7m of the rear boundary. Was missing from draft. Note: A.1(h)(ii) was substituted by SI 2016/332.
6. **`article_2_3_no_multi_storey_rear`** (A.2(c)) — on Art 2(3) land, multi-storey rear extensions not permitted. Draft had this but it was merged with the side extension rule; now separated.
7. **`roof_pitch_match_multi_storey`** (A.3(c)) — roof pitch of multi-storey enlargement must match original so far as practicable. Added as interpretive.
8. **`cumulative_enlargement_ja`** (A.1(ja)) — total enlargement including existing joined extensions must not exceed A.1(e)–(j) limits. Was an interpretive note; now a proper interpretive rule with correct citation.

### Rules corrected
- **`larger_extension_not_on_article_2_3_or_sssi`**: The legislation says A.1(g) applies to houses "not on article 2(3) land **nor on a site of special scientific interest**". The draft cited only article 2(3) land. Added SSSI to description. Also noted that the basic limit for a **detached** house on Art 2(3) land is actually 4m not 3m — the rule conservatively uses 3m as a worst-case threshold pending a dwelling_type split.
- **All citation sub-paragraphs**: Added precise sub-paragraph letters (A.1(b), A.1(c), etc.) to every rule. Draft had placeholders only.

### A.2(d) — cumulative enlargement on Art 2(3) land
A.2(d) (inserted by SI 2017/391) states that on Art 2(3) land, the total enlargement (including any existing joined enlargement) must not exceed the limits in A.2(b) and (c). This is covered by the `cumulative_enlargement_ja` interpretive rule which flags needs_review; a future rule could make this more explicit.

---

## Rules kept as interpretive (cannot auto-decide)

| Rule | Reason |
|------|---------|
| `materials_similar_in_appearance` | Requires knowing actual materials used |
| `upper_floor_side_windows` | Requires knowing window specification |
| `roof_pitch_match_multi_storey` | Requires knowing roof pitch details |
| `cumulative_enlargement_ja` | Requires planning history of previous extensions |
| `original_dwellinghouse_definition` | Requires knowing when house was built and what extensions pre-exist |
| `planning_conditions_removing_rights` | Requires checking full planning history |

---

## Classes NOT in scope (Part 1 only, Class A only)

The uploaded file also contained:
- **Class AA** — upward extensions (additional storeys). Distinct prior approval regime. Out of scope for MVP.
- **Class B** — roof additions (dormers etc.). Out of scope for MVP.
- **Class C** — other roof alterations. Out of scope.
- **Class D** — porches. Out of scope.
- **Class E** — outbuildings. Out of scope.
- **Class F** — hard surfaces / driveways. Out of scope.
- **Class G** — chimneys/flues. Out of scope.
- **Class H** — microwave antennas. Out of scope.

Future versions could add Classes B and E, which appear frequently in Sheffield LDC cases.

---

## Open questions for later

1. **Detached vs non-detached on Art 2(3) land**: The 3m/4m basic limit split by dwelling type should also apply within the `larger_extension_not_on_article_2_3_or_sssi` rule. Currently conservative at 3m for all.
2. **SSSI dataset**: planning.data.gov.uk does not publish SSSI boundaries under OGL. Natural England publishes them via their open data portal. Need to verify licence before use.
3. **A.1(a) exclusion field**: Added `permitted_use_only` field to `Proposal` dataclass — needs adding to engine and tests.
4. **`built_under_part_20` field**: New field added to rules — needs adding to `Proposal` dataclass and tests.
5. **`distance_to_rear_boundary_m` field**: New field for A.1(h)(ii) rule — needs adding to `Proposal` dataclass and tests.
6. **`includes_verandah_balcony_platform` field**: New field for A.1(k)(i) rule — needs adding to `Proposal` dataclass and tests.
