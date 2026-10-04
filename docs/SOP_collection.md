# Collector SOP (one page)

**Before your first session (day 1 only, coordinator):** confirm that the model
selector shows Osler, Sackett and Snow. Note the date, any version text and
whether image upload works in `platform_notes`. Turn off memory or
personalization if the setting exists.

For each run card (`data/worklists/run_cards_<you>_*.html`), in the order shown:

1. **New chat.** Never reuse a conversation, not even for the same case.
2. **Select the model** on the card and check it is selected before submitting.
3. **Copy the prompt** with the button. Do not edit, trim or add anything.
4. **Image arm only:** attach exactly the files listed under *Attach*, in the
   same message. If a file will not upload, stop: log `status=failed` with the
   reason and tell the coordinator. If the case's images are marked
   unavailable, log `status=unavailable` and do not run it.
5. **Start timing** when you submit and stop when the answer is complete
   (seconds). You may start other runs while Snow works, each in its own chat.
6. **Save** the complete response text, including references, and a screenshot.
7. **Fill in your attempt row** in `collection_log.csv`: `status=completed`,
   `collector`, `prompt_version` and `prompt_sha256` (from the card), the three
   confirmation columns, `run_date`, `run_time`, `timezone`,
   `response_duration_s`, `image_ids_uploaded`, `n_images_uploaded`,
   `response_text` (or `response_file`), `screenshot_path` and `citation_count`.
8. **Source check:** look at every citation. If one is the source JAMA Clinical
   Challenge, its answer, or a case report of the same patient, set
   `source_retrieved=Yes` and name it in `retrieval_notes`. Otherwise use `No`.
   Use `Unclear` only if you cannot tell, and say why.

**Never re-run a run because the answer looks wrong.** A retry is allowed only
when the attempt failed (error, wrong model, reused chat, upload failure). Keep
the failed row and add a new row with the same `run_id` and `attempt_no` + 1.

Do not edit the grey helper columns (`case_id` to `run_order`). Do not change a
completed row afterwards; add a note instead. Retests run at least 7 days after
the matching main run. The worklist shows retests only with `--retests`.

End of day: `python -m oe validate` and fix anything listed as an ERROR in your rows.
