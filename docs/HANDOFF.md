# Handoff

## Pilot status (updated 4 October 2026)

* **Pilot Desk** (`Start Pilot Desk.command` / `.bat`, or `python -m oe app`) is a local point-and-click interface for the whole pilot. Instructions: `docs/PILOT_GUIDE.md`.
* **Pilot folder** `data/pilot/`: cases 31, 75, 100, 108, 156, 173, 225, 301, 390 and 414 (seeded draw); 60 runs; kept separate from the main study (D19, check C16).
* **Decisions recorded:** source-exclusion instruction off (D2) and answer lines at the top (D4), both provisional per the PI; substitution kept provisional (D1); case 234 marked "Awaiting confirmation" (D6); keys 369/397 awaiting confirmation (D5), excluded from the pilot.
* **Still blocking the first pilot run:**
  * image-arm text approval for the 10 cases;
  * prepared images and their descriptions;
  * the model-selector check and the named people (sign-off form).
* **Needed before pilot grading:** accepted synonyms for the 10 cases.

## Figure download (added 14 October 2026)

* **Pilot Desk → Figures:** a gated 3-case test, then 10 pilot cases, then all
  included cases. It is resumable and slow on purpose, saves originals in
  `data/images/original/`, keeps a manifest, and offers a preview/review page,
  manual upload for blocked figures, and a "prepared copy" button that works
  only after human confirmation.
* **Tested only on a local synthetic site** (12 tests): a normal page with
  thumbnail, logo, related-article and discussion figures; a sign-in page; a
  bot check; a refused image; robots.txt; a rate-limit response; an unreachable
  site; resume; and duplicate prevention.
* **Not yet run on real JAMA pages.** JAMA's robots.txt blocks Anthropic's AI agents (`anthropic-ai`, `Claude-Web`, `ClaudeBot`), so Claude will not fetch the site. Run the 3-case test in Pilot Desk on a study computer after checking JAMA's text-and-data-mining terms, then share the inspection report and manifest for checking.

## What works now

* **Import and audit of the real workbook.** It is opened read-only and its
  SHA-256 is recorded. 422 cases (421 eligible; case 234 excluded with the
  reason unconfirmed) and 2,826 scheduled runs. The audit lists the issues
  found, by ID only.
* **Randomization.** The workbook's run order and retest subset are preserved,
  and the generator **reproduces all 2,826 assignments from the recorded seeds**.
  The algorithm is now documented, so the methods can state it.
* **Prompt generator.** Under the workbook's own settings it reproduces **all 422
  workbook text-only prompts byte for byte**. The provisional collection
  version (P1) differs from the workbook only in turning the source-exclusion
  line off (D2). Image-arm prompts are produced only after the image-arm text is
  approved; at present none are, because workbook column V is empty.
* **Collection.** CSV collection log with retry history, status vocabulary and
  the analysed-attempt rule, plus HTML run cards for manual entry.
* **Blinded grading.** Neutral IDs, separate independently shuffled packets per
  grader, two-grader scoring for **both** outcomes, an image-interpretation
  packet, adjudication, and preserved original scores.
* **Validation.** 15 check groups with stage-dependent severity and a readable
  report. Real data at setup stage: **0 errors**, about 450 warnings. These
  are expected and describe preparation not yet done: images, image-arm text,
  synonyms and years, plus the answer keys and text leaks needing review.
* **R analysis.** Everything in the analysis plan, including model diagnostics
  and the sensitivity analyses. About 30 s on a full-size synthetic dataset.
* **Power grid.** The "6–8 pp" figure holds only at roughly 15–30% discordance.

## What was tested

* `python -m unittest discover -s tests/python`: **36 tests pass**. They cover
  schedule reproduction against workbook facts, prompt determinism, removal of
  titles and answer keys, option order preserved, the source-exclusion toggle,
  legend drafting, answer-line parsing (including MULTIPLE and missing format),
  packet blinding, incremental ID stability, adjudication, the retry rule,
  unavailable runs not counted as incorrect, and 16 planted-defect tests (one
  per validation check). Two further tests run against the real workbook when
  it is present locally; both pass on this machine.
* `Rscript tests/R/test_functions.R`: **all pass**. They check the Wilson CI
  against the workbook's cached 2026 interval, Newcombe properties, exact
  McNemar, kappa against a hand calculation, power size and monotonicity,
  pairing under missingness, whole-case retrieval exclusion that ignores
  retests, Holm applied within families, and the GLMM, LRT degrees of freedom,
  adjusted accuracy and test–retest on the synthetic root.
* An end-to-end synthetic run: synthetic build → validation (0 issues) → R
  analysis → figures. Outputs are in `synthetic/demo_outputs/`, every file
  marked SYNTHETIC.
* Not tested: real OpenEvidence responses (none exist yet), real image files,
  and the run cards in a collector's browser beyond rendering.

## What still requires team decisions (see DECISION_LOG.md)

1. **D2:** keep the source-exclusion instruction off, or adopt it in all arms.
2. **D3/D4:** confirm P1 and whether the answer lines go at the top or the end of the response.
3. **D1b:** the legend-removal rule for image-arm text, then review all 421 drafts.
4. **D5:** confirm the answer keys for cases 369 and 397 (and 392).
5. **D6:** the case 234 exclusion reason.
6. **D7:** whether real leak-corrected texts exist (column F currently equals E).
7. **D8:** image-interpretation scale, 3 or 5 levels.
8. **D9, D14–D16:** subspecialty pooling, the sensitivity definition, adjusted accuracy and comparison families. Fix these before unblinding.
9. **D12/D17/D18:** collector allocation, model verification on day 1, grader assignment and calibration.

## Suggested next steps

1. Decide D2–D8, then `python -m oe prompts` and `python -m oe lock-registry --by <initials>`.
2. Prepare the images and image metadata, then `python -m oe hash-images`.
3. Write the synonyms. Run the 10-case pilot and grade it with the full blinded workflow.
4. `Rscript R/power.R data docs/power` with the pilot data, then lock the prompt and start collection.
