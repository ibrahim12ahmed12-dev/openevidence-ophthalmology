# Implementation checklist

Sources reviewed (4 October 2026):

* `OpenEvidence_Model_Family_..._Study_Methodology.pdf` (methodology, 2 October 2026).
* `..._Study_Methodology_1.pdf`. **Despite its file name, this is the *Workbook Guide*, not a second methodology version.**
* `2026_10_03_OpenEvidence-Data_ModelFamily.xlsx`. The actual workbook was inspected sheet by sheet: formulas, cached values, validations and the 2026 prompt sheets.

## 1. Already specified

* A 3 × 2 within-case design. 421 eligible cases of 422 (case 234 is excluded). 2,526 main runs, 300 retest runs (50 cases × 6), 2,826 scheduled.
* Run order randomized within each case (seed 20261002). Retest subset seed 2026.
* Image arm: substitution (Option A). No case titles in the inputs.
* Primary outcomes: diagnosis (first-listed only, published diagnosis or accepted synonym) and management letter. Partial correctness is recorded and scored incorrect in the primary analysis.
* Two independent graders and a third adjudicator. Kappa per outcome.
* Primary model: mixed logistic regression with model × input + subspecialty + case random intercept. McNemar with Holm. Wilson CIs.
* Source-retrieval flag per response. Sensitivity analysis excludes retrieved cases.
* Historical 2026 results. **Verified against the workbook**: diagnosis 200/421, management 283/421, management 161/200 given a correct diagnosis and 122/221 given an incorrect one. Used only as historical.

## 2. Implemented now (reversible, tested)

| Component | Where | Verified |
|---|---|---|
| Read-only workbook import, header checks, source SHA-256 manifest | `oe/importer.py` | real workbook: 422 cases, 2,826 runs |
| Case registry, separate private answer key, human-edited annotation, image-arm and image files | `data/registry/` | - |
| Readable workbook audit (IDs and counts only) | `data/reports/workbook_audit.md` | - |
| Schedule that preserves the workbook assignments **and** reproduces them from the recorded seeds | `oe/schedule.py`, `schedule/run_schedule.csv` | **identical** for all 2,826 rows; algorithm documented |
| Deterministic, versioned prompt generator with SHA-256 per prompt | `oe/prompts.py`, `config/prompt_versions/` | **byte-identical to all 422 workbook prompts** under workbook settings |
| Draft legend removal with non-visual-detail flags (never auto-approved) | `oe/legend.py` | real data: drafts for 422 cases; 118 with no clear legend, flagged |
| Attempt-level collection log, status vocabulary, retry history, analysed-attempt rule | `oe/collection.py` | tests |
| HTML run cards (copy prompt, files to attach, checklist) | `oe/worklist.py` | manual |
| Answer-format parser (pre-fill only) | `oe/extract.py` | tests |
| Blinded per-grader packets for **both outcomes**, image-interpretation packet, merge, adjudication | `oe/grading.py` | tests |
| Long analysis dataset (one row per scheduled run, statuses kept) | `oe/build.py` | tests |
| 15 validation check groups and a Markdown/CSV issue report | `oe/validate.py` | 16 planted-defect tests (plus blinding, adjudication and unapproved-text tests) |
| R analysis: accuracy, paired McNemar/Holm/Newcombe, GLMM + LRTs + ORs + simple effects + adjusted accuracy, diagnostics, sensitivity S1–S3, all secondary analyses | `R/` | R tests; full synthetic run |
| Power / minimum detectable difference | `R/power.R`, `docs/power/` | grid computed |

## 3. Missing (needed before or during collection)

* Prepared image files and image metadata (`images.csv`). None were supplied.
* Approved image-arm text for every case (workbook column V is empty).
* Accepted diagnosis synonyms (column W is empty). Required before grading.
* Publication year. The workbook has no column for it.
* Number of figures and imaging modality per figure (X–Z are empty).
* Exclusion reason for case 234.
* Any leak-corrected texts that differ from the originals (see D7).
* Collector and grader assignments, the collection window, and pilot results.
* Confirmation that the three models and the image upload work as described.

## 4. Contradictions found

| # | Between | Finding | Resolution in this workflow |
|---|---|---|---|
| 1 | Methodology vs workbook | The methodology says the text-only arm "reproduces the 2026 input exactly". The workbook differs: titles removed; answer-format line added; source-exclusion line added by default; 11 cases (5, 10, 106, 124, 132, 155, 159, 175, 365, 391, 420) were shortened in 2026 and now run in full; 151 of the 422 stored 2026 prompts lack the instruction prefix. | **Exact replication is not claimed.** Differences are listed in the methods draft. Osler text-only vs 2026 is descriptive only. |
| 2 | Workbook guide vs workbook | "Leak-fixed rerun text" (F) is filled for 81 cases but identical to the original text (E) in all 81. | D7 (open) |
| 3 | Methodology vs workbook | Two graders for **both** outcomes vs one management-letter column with formula scoring; the kappa summary covers diagnosis only. | Two independent management grades plus adjudication; kappa for both outcomes. |
| 4 | Methodology vs workbook formula | A response naming several options or none should be "incorrect", but the workbook leaves blank letters as missing (dropped from the denominator). | MULTIPLE/NONE coded and scored 0 by graders (D10). |
| 5 | Workbook README vs this brief | Source-exclusion instruction "added to both arms" vs "do not silently introduce". | Off by default; open decision D2. |
| 6 | Methodology vs workbook | Image-interpretation scale: 3 levels vs 5 categories. | D8 |
| 7 | Methodology/workbook vs this brief | Test–retest kappa "per model" (workbook pools inputs) vs per condition. | Per condition and outcome (12 estimates); per-model pooling is easy to add. |
| 8 | Workbook formula vs this brief | Retrieval flag counts retest runs too. | Main runs only (D14). |
| 9 | Workbook vs answer text | Case 397: stored letter disagrees with the published answer text. Case 369: the published answer has no letter. The J column is typed (not a formula) in 165 rows. | Flagged for human confirmation (D5). Nothing changed. |
| 10 | Workbook vs this brief | Summary sheet reports **mean** response time. | Median and IQR. |
| 11 | Methodology vs workbook | Case 234 "excluded for the same reason as 2026, stated explicitly" vs "confirm reason". | Flag kept; reason not invented (D6). |
| 12 | Workbook Run Log vs needs | No fields for time of day, timezone, prompt version, screenshot, run status, attempts, image IDs, second management grade or retrieval assessor. | Added in the CSV collection log. The workbook can still be used as a viewer. |
| 13 | Methodology claim | "6–8 pp detectable at 80% power" | Holds only for discordance of about 15–30% (`docs/power/power_report.md`). Unverified until the pilot. |

Other workbook observations: titles appear verbatim inside the case text for
cases 74, 178, 289, 320, 389, 394, 406 and 417. The reference diagnosis appears
verbatim in the text for cases 45, 151, 277, 278 and 397 (and 234). These are
flagged as validation warnings for human review; nothing is auto-edited. Two
different cases share the title "A Painful Red Eye"; IDs are used throughout.

## 5. Decisions that could change the scientific interpretation

1. **What the input contrast means (D1/D1b).** It compares substitution, not
   addition. The legend-removal rule determines how much written visual
   information is left in the image arm.
2. **Source-exclusion instruction (D2).** It affects comparability with 2026,
   realism, and possibly retrieval itself.
3. **Prompt style and answer-first format (D3/D4).** They may shift accuracy
   relative to 2026 and differently by model.
4. **Answer keys (D5) and synonym lists.** They determine what counts as correct.
5. **Retrieval sensitivity definition (D14).** Snow is expected to retrieve most,
   so this choice affects the model comparison.
6. **Comparison families and the adjusted-accuracy definition (D15/D16).** Fix
   them before unblinding.
