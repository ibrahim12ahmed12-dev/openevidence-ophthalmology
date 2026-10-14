# OpenEvidence model family on JAMA Ophthalmology Clinical Challenges: study workflow

This repository holds the tools for a 3 × 2 within-case study. Each eligible JAMA
Ophthalmology Clinical Challenge is run under six conditions: three OpenEvidence
models (Osler, Sackett, Snow) × two inputs (text only, text plus images). The
tools cover data preparation, collection support, blinded grading, quality checks
and the statistical analysis.

> **No study results are in this repository.** Collection has not started. The
> only numbers here are (a) the historical 2026 results, which are labelled as
> historical everywhere, (b) planning calculations, and (c) outputs from
> **synthetic** data, which are marked "SYNTHETIC" in every file and figure.

> **This repository is public. Never commit real study data.** Case text,
> answer keys, prompts, model responses and grades stay in `data/` (git-ignored).
> The evaluated models search the web, so publishing answer keys here could
> contaminate the benchmark, and the JAMA text is copyrighted. Only code, ID-only
> schedules, empty templates and synthetic demos are committed.

## Start here if you do not code: the 10-case pilot

Double-click **Start Pilot Desk** (`.command` on Mac, `.bat` on Windows). It
opens point-and-click pages in your browser for:

* reviewing image-arm text,
* describing images,
* recording the six OpenEvidence runs per case,
* confirming answer keys,
* running the checks,
* exporting blinded grading packets and combining returned grades.

It runs only on your computer. Step-by-step instructions are in
**[docs/PILOT_GUIDE.md](docs/PILOT_GUIDE.md)**. Pilot data stay in
`data/pilot/`, separate from the main study.

## What is where

| Path | What it is |
|---|---|
| `docs/IMPLEMENTATION_CHECKLIST.md` | What is specified, what was built, what is missing, contradictions found |
| `docs/DECISION_LOG.md` | Every provisional default and every decision the team still owes |
| `docs/DATA_DICTIONARY.md` | Every file and column |
| `docs/PILOT_GUIDE.md` | Plain-language pilot instructions (Pilot Desk) |
| `docs/SOP_collection.md`, `docs/SOP_grading.md` | One-page instructions for collectors and graders |
| `docs/METHODS_DRAFT.md` | Methods text describing only the workflow as built |
| `docs/HANDOFF.md` | What works, what was tested, what is still open |
| `docs/power/` | Power / minimum-detectable-difference grid (assumptions stated) |
| `config/study_config.json` | Locked settings: conditions, seeds, prompt switches, comparison families |
| `config/prompt_versions/` | Versioned prompt wording (P1 = provisional collection version, P0 = candidate) |
| `oe/` | Python workflow (standard library only, plus `openpyxl` for the workbook import) |
| `R/` | Statistical analysis, figures, power calculation |
| `schedule/run_schedule.csv` | The randomized run schedule (IDs only, safe to publish) |
| `templates/` | Empty collection, grading, adjudication and metadata templates; manuscript tables |
| `synthetic/demo_outputs/` | Analysis report, tables and figures from SYNTHETIC data |
| `tests/` | Python and R tests (all fixtures are synthetic) |
| `data/` | **Local only.** Real workbook, registry, prompts, collection log, grades |

## One-time setup

1. Install Python 3.9+ and R 4.2+.
2. Install the packages:
   ```bash
   pip install openpyxl                      # only needed for the workbook import
   Rscript -e 'install.packages(c("lme4","emmeans","ggplot2","jsonlite","testthat"))'
   ```
3. Copy the study workbook into `data/source/`. The workbook is never modified.
4. Import it and build the derived files:
   ```bash
   python -m oe import                      # registry, answer key, audit -> data/
   python -m oe schedule                    # keeps the workbook's randomization; checks it against the seeds
   python -m oe draft-image-text            # draft legend-removed text for human review
   python -m oe prompts                     # collector-facing prompts (active version)
   python -m oe init-log                    # empty collection log, one row per scheduled run
   python -m oe validate --stage setup      # writes data/reports/validation_report_setup.md
   ```
5. Run the tests: `python -m unittest discover -s tests/python` and
   `Rscript tests/R/test_functions.R`.

The audit in `data/reports/workbook_audit.md` lists case IDs and counts only.

## Before collection starts (prep team)

* **Decisions.** Settle the open items in `docs/DECISION_LOG.md`. At minimum: the
  source-exclusion instruction (D2), the prompt style and answer-format placement
  (D3/D4), the answer keys for cases 369 and 397 (D5), and the case 234 reason (D6).
* **Image-arm text.** Edit `data/registry/image_arm_text.csv` using
  `image_arm_review_DRAFT.csv`. The draft only suggests which paragraph is the
  legend and lists non-visual details (age, laterality, timing) found in it. A
  person decides what moves back into the vignette and sets `status=approved`
  and `approved_by`. Image-arm prompts are generated only for approved rows.
* **Images.** Put prepared files in `data/images/prepared/` with neutral names
  (`IMG-<case>-<n>.png`) and fill in `data/registry/images.csv`: modality,
  availability, preparation steps, and caption/label sign-off. Then run
  `python -m oe hash-images`. Keep the originals unchanged elsewhere. If a figure
  cannot be uploaded (for example, video only), set `availability=unavailable_video_only`.
* **Synonyms and years.** Fill in `data/registry/case_annotations.csv`. Accepted
  synonyms must be written before grading begins.
* **Lock.** Run `python -m oe lock-registry --by <initials>`. From then on, any
  change to a case ID, text, option or key is flagged as an error. Set
  `"locked": true` in the config after the pilot.
* **Pilot.** Run 10 cases in all six conditions. Afterwards, run
  `Rscript R/power.R data docs/power` to get discordance-based planning numbers.

## Daily collection (collectors)

1. `python -m oe worklist --collector C1` writes `data/worklists/run_cards_C1_next.html`.
   Each card shows the model, the input, the files to attach, the locked prompt
   with a Copy button, and a checklist.
2. In OpenEvidence, use a **new chat** for every run and select and confirm the
   model. Paste the prompt unchanged, attach the listed images (image arm only),
   time the response, and save the full text and a screenshot.
3. Fill in the run's row in `data/collection/collection_log.csv` (see
   `docs/SOP_collection.md`). A failed attempt stays in the log: add a new row
   with the same `run_id` and `attempt_no` + 1. The analysis uses the **first
   completed** attempt. Never re-run a run because its answer looked wrong.
4. At the end of the day: `python -m oe validate` and `python -m oe progress`.

Do not automate OpenEvidence. All runs are entered by hand through the web
interface from a verified clinician account.

## Grading (coordinator, two graders, adjudicator)

```bash
python -m oe packets                 # new neutral response IDs + one packet per grader
# graders return their filled packets to data/grading/returns/
python -m oe merge-grades            # finds disagreements -> adjudication packet
# adjudicator fills data/grading/adjudication/adjudication_return.csv
python -m oe merge-grades            # final scores (originals and reasons are kept)
```

Packets contain no model, input, condition, run type, dates or durations. Each
grader receives a separately shuffled file with no column for the other grader's
score. Both outcomes (diagnosis and management) are graded independently by both
graders. See `docs/SOP_grading.md`.

## Analysis

```bash
python -m oe validate --stage analysis --strict   # must pass with 0 errors
python -m oe build-analysis                       # data/analysis/analysis_dataset.csv
Rscript R/run_analysis.R data outputs             # report, tables, figures -> outputs/ (git-ignored)
```

To try the analysis on synthetic data:

```bash
python -m oe synthetic                            # synthetic/demo_data (regenerated, git-ignored)
Rscript R/run_analysis.R synthetic/demo_data synthetic/demo_outputs
```

## Ground rules built into the tools

* Original source files are never modified. Derived files are separate, and
  human-edited files are never overwritten.
* Model inputs never include case titles, reference answers, discussions or
  revealing file names. Answer options are passed verbatim and in their published order.
* An unperformed or unavailable run is never scored as incorrect. A missing
  answer-format line is flagged for a grader and is never auto-scored.
* Repeated runs are never treated as independent cases. Pairing is kept, and
  retests are analysed separately.
* Software flags problems. People decide synonyms, clinical correctness and
  scientific choices.
