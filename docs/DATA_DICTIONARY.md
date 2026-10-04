# Data dictionary

All files are UTF-8 CSV. Paths are relative to a data root (`data/` for real
data, `synthetic/demo_data/` for the demo). **G** = generated (rewritten by the
tools; do not edit). **H** = human-edited (seeded once, never overwritten).
**P** = private (coordinator only; never sent to collectors or graders).

## registry/case_registry.csv (G): one row per source case (422)

| Column | Meaning |
|---|---|
| case_id | Stable integer ID (= workbook `Case ID`, column R). Never changes. |
| source_row | Workbook row (audit only) |
| eligible | Yes/No, from workbook column S |
| exclusion_reason | "Awaiting confirmation" when the workbook note asks for confirmation or is blank; otherwise the workbook reason. Never invented. |
| exclusion_reason_workbook | Workbook column T, verbatim |
| subspecialty | The 2026 classification, unchanged (10 groups) |
| publication_year | Copied from annotations at build time (blank in the registry) |
| source_url | Article link. Never shown in model inputs. |
| original_text | Workbook column E, verbatim |
| leak_corrected_text | Workbook column F, verbatim (81 cases; identical to E, see D7) |
| leak_corrected_identical_to_original | Yes/No/blank |
| text_only_input | F if filled, else E (mirrors workbook column U) |
| text_source | Which column supplied `text_only_input` |
| answer_options | Published options, verbatim and in their published order |
| n_options | Parsed option count (expected 4) |
| options_sha256, text_only_sha256 | Fingerprints used by the registry lock (check C04) |
| retest_subset_workbook | Workbook column AA |
| hist_prompt_had_prefix_2026 | Whether the stored 2026 prompt began with the PS+ prefix |
| hist_text_truncated_2026 | Whether the 2026 prompt lacked part of the case text |
| hist_title_included_2026 | Whether the 2026 prompt contained the title |

## registry/answer_key_PRIVATE.csv (G, P)

`case_id, case_title, reference_diagnosis, correct_letter` (workbook J), plus
`correct_letter_from_text` (best-matching option, audit only) and `key_check`
(`OK` or `REVIEW: ...`). Also `correct_answer_text` (the first line of
workbook I), `answer_key_explanation` (the rest of I) and `discussion`.

## registry/answer_key_confirmations.csv (H)

One row per answer key flagged by the import audit: `case_id,
workbook_letter, issue, confirmed_letter, confirmed_by, confirmed_date,
evidence_note`. When `confirmed_letter` is filled (in Pilot Desk → Answer
keys), it replaces `correct_letter` in the private answer key, with
`key_check = "CONFIRMED <letter> by <initials> <date>"`. The workbook is never changed.

## registry/case_annotations.csv (H)

`case_id, publication_year, accepted_dx_synonyms` (semicolon-separated; written
**before** grading), `synonyms_finalized_by, synonyms_finalized_date, n_figures, notes`.

## registry/image_arm_text.csv (H)

| Column | Meaning |
|---|---|
| image_arm_text | Case text with figure legends removed and needed non-visual details moved into the vignette; figures cited as "(Figure N attached)" |
| status | `not_started`, `draft_needs_review`, `workbook_entry_pending_signoff`, `approved`. Only `approved` produces a prompt. |
| edited_by, approved_by, approved_date, review_notes | Audit trail |

`registry/image_arm_review_DRAFT.csv` (G) holds the automatic proposal:
`draft_image_arm_text, removed_segments, nonvisual_details_in_removed,
review_flags, draft_confidence`.

## registry/images.csv (H): one row per uploaded image file

| Column | Meaning |
|---|---|
| image_id | Neutral ID `IMG-<case>-<n>`. Used in prompts and logs. |
| figure_number, panels | Which published figure and panels |
| original_filename | The source file as published (kept unchanged elsewhere) |
| prepared_filename | The file actually uploaded. Neutral name, no diagnosis words (check C08). |
| prepared_sha256 | Filled by `python -m oe hash-images`; detects later changes (C09) |
| modality | One or more, `;`-separated, from: Fundus photography, OCT, Slit lamp / anterior segment, Fluorescein / ICG angiography, Visual fields, CT / MRI, External photography, Histopathology, Ultrasound, Electrophysiology, Other |
| availability | `available`, `unavailable_video_only`, `unavailable_other` |
| unavailable_reason | Free text |
| width_px, height_px | Resolution of the prepared file |
| preparation_steps | For example "cropped panel letters and caption; arrows kept; split into 2 for upload limit" |
| label_or_caption_flag | `needs_review` or `cleared` (person checked for diagnosis-revealing text) |
| label_review_by, notes | Audit trail |

## schedule/run_schedule.csv (G): one row per scheduled run (2,826)

`run_id` (`NNN-Ck`, plus `-R` for retests), `run_type` (Main/Retest),
`case_id, condition` (1–6), `model, input` (text_only/text_image), `run_order`
(1–6 within the case and run type), `linked_main_run_id` (retests),
`retest_min_interval_days` (7), `assignment_source` (workbook/generated), and
`collector_assigned, batch` (coordinator-entered; kept across rebuilds).

## prompts/prompts_<version>.csv (G): collector-facing

`case_id, input, prompt_version, prompt_sha256, ready` (Yes/No),
`not_ready_reason, image_ids_to_upload, prepared_files_to_upload, n_chars,
prompt_text`. A manifest JSON records the spec hash, settings and registry hash.

## collection/collection_log.csv (H): one row per ATTEMPT

| Column | Meaning / allowed values |
|---|---|
| run_id, attempt_no | Key. Retry = new row, attempt_no + 1. |
| case_id, run_type, condition, model, input, run_order | Helper copies of the schedule. **Do not edit**; checked against the schedule. |
| status | blank = pending; `completed`, `failed`, `unavailable`, `withdrawn` |
| failure_reason | Required for failed, unavailable or withdrawn |
| collector | Initials/ID |
| prompt_version, prompt_sha256 | Copied from the run card |
| model_selection_confirmed, new_session_confirmed, memory_personalization_off | Yes/No |
| run_date, run_time, timezone | `YYYY-MM-DD`, `HH:MM` (24 h, local), IANA zone such as `America/New_York` |
| response_duration_s | Seconds from submit to complete answer |
| image_ids_uploaded | `;`-separated image IDs actually attached |
| n_images_uploaded, upload_limit_note | Count; any limit encountered |
| response_text | Full response, including the citations list |
| response_file | Alternative to response_text: path to a .txt file |
| screenshot_path | Path to the screenshot(s) |
| citation_count | Integer ≥ 0 |
| source_retrieved | `Yes` / `No` / `Unclear`. Yes = a citation is the source Clinical Challenge, its answer discussion, or a case report of the same patient. |
| retrieval_assessed_by, retrieval_notes | Who checked; which citation |
| platform_notes, notes | Banner messages, UI changes, anything unusual |

**Derived run status**: completed if any attempt is completed (the first one
is analysed); otherwise withdrawn, then unavailable, then failed; otherwise
pending.

## grading/

| File | Contents |
|---|---|
| private/response_key_PRIVATE.csv (P) | `response_id ↔ run_id, attempt_no, case_id` |
| private/packet_issue_log.csv (P) | Which response went to which grader, in which batch |
| extraction_auto.csv (P) | Parser output per response (`auto_diagnosis, auto_letter, format_complete, extraction_flags`) |
| packets/grader_<G>_batch_<B>.csv | Packet for one grader (see below) |
| packets/interp_<G>_batch_<B>.csv | Image-interpretation packet (image-arm responses only) |
| packets/responses/<RSP-id>.txt | Response text only |
| returns/ | Graders save completed packets here (same file name) |
| adjudication/adjudication_packet.csv | Disagreements, with both graders' scores and reasons |
| adjudication/adjudication_return.csv | Adjudicator's completed copy |
| grades_final.csv (P) | Per response: `dx_g1, dx_g2, dx_adjudicated, dx_final, dx_final_source` (agreement / adjudicated / awaiting_adjudication / awaiting_grades); the same for `mgmt_` and `partial_`; `mgmt_letter_g1/g2`; `interp_g1/g2/final` |

Packet columns filled by graders: `grader_id`, `extracted_diagnosis_confirmed`
(first-listed diagnosis as the grader reads it), `dx_correct` (0/1),
`dx_partial` (0/1; right category, wrong entity), `dx_reason`, `mgmt_letter`
(A–D, MULTIPLE, NONE), `mgmt_correct` (0/1), `mgmt_reason`,
`flag_for_discussion`, `graded_date`. Image packet: `interp_category` (Correct,
Partly correct, Incorrect, Invented findings, Not described) and `interp_reason`.

## analysis/analysis_dataset.csv (G): one row per scheduled run

Schedule columns, plus `eligible, subspecialty, subspecialty_covariate`
(pooled < 20), `publication_year, modalities, run_status, n_attempts,
attempt_no_used, collector, prompt_version, run_datetime_utc,
response_duration_s, citation_count, source_retrieved, n_images_uploaded,
response_id`, the grade columns from grades_final, `analyzable_dx /
analyzable_mgmt` (1 = completed, final grade present, eligible case),
`elapsed_days_since_main` (retests) and `synthetic` (TRUE/FALSE).

## Historical file

`registry/historical_2026_PRIVATE.csv` (G, P) holds the archived 2026 per-case
scores (workbook O–Q). It is **never merged into the new analysis dataset**
(check C15). The R analysis uses only the aggregate counts in
`config/study_config.json → historical_2026`.

## pilot/ (separate data root for the 10-case pilot)

`data/pilot/` has its own `schedule/` (run IDs `P-NNN-Ck`, run_type `Pilot`,
same within-case order as the main schedule), `prompts/`,
`collection/collection_log.csv` (plus `responses/` and `screenshots/` saved by
Pilot Desk), `grading/` and `reports/`. Its registry, answer key, annotations,
image-arm text and images are **shared** with `data/`
(`config_override.json → shared_registry_root`), so preparation carries over.
`pilot_signoff.json` records the model-selector check and named
collectors/graders. `PILOT_README.md` marks the folder as pilot data. Check C16
fails if pilot runs ever appear in the main collection log.
