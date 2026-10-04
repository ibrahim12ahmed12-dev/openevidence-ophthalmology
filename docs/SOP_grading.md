# Grader SOP (one page)

You receive your own packet (`grader_<you>_batch_<date>.csv`) and a
`responses/` folder. Each row has a neutral response ID. You will not see which
model or input produced it, and you will not see the other grader's scores.
Do not discuss cases with the other grader until both packets are returned.

For every row:

1. **Read** `auto_diagnosis` and `auto_letter`. These are machine-parsed from
   the "Diagnosis:/Next step:" lines and only a starting point. If
   `extraction_flags` is not empty, or the values look wrong, open
   `response_file` and read the response.
2. **Diagnosis.** Score only the **first-listed** diagnosis. Copy it into
   `extracted_diagnosis_confirmed`.
   * `dx_correct = 1` if it matches `reference_diagnosis` or one of the
     `accepted_dx_synonyms`. Otherwise 0.
   * `dx_partial = 1` if it is in the right disease category but names the wrong
     specific entity (scored 0 for the primary outcome). Leave it 0 when
     `dx_correct = 1`.
   * Write a short `dx_reason` whenever your decision is not obvious.
3. **Management.** Record the option the response selects in `mgmt_letter`:
   A–D, or `MULTIPLE` (more than one option chosen), or `NONE` (no option
   chosen anywhere in the response). Then set `mgmt_correct` = 1 only if the
   letter equals `correct_letter`. MULTIPLE and NONE are always 0.
   A missing format line is **not** an error in itself: read the response first.
4. Set `grader_id` and `graded_date`. Use `flag_for_discussion` for anything
   the adjudicator should see.
5. Save the file unchanged in name and columns into `grading/returns/`.

**Image-interpretation packet** (image-arm responses only; you will know these
included images). Using the attached image files, choose one category for how
the response describes the image findings: Correct, Partly correct, Incorrect,
Invented findings (describes findings that are not present), or Not described.

**Adjudicator.** For each row in `adjudication_packet.csv`, read the response and
both graders' scores and reasons. Fill in only the `adj_` columns for the
outcomes listed in `outcomes_in_disagreement`, plus `adj_reason` and
`adjudicator_id`, and save as `adjudication_return.csv`. The original grader
scores are never changed.
