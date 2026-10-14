# SYNTHETIC DEMONSTRATION - NOT STUDY RESULTS

Every number below comes from randomly generated data and says nothing about OpenEvidence.

# Analysis report

Generated: 2026-10-04 22:16 UTC | data root: synthetic/demo_data

## Run flow

- Scheduled main runs: 2526
-   of which eligible cases: 2526
- Completed: 2520
- Unavailable (e.g. image cannot be uploaded): 6
- Failed without completed retry: 0
- Pending: 0
- Withdrawn: 0
- Analysable - diagnosis: 2520
- Analysable - management: 2520
- Scheduled retest runs: 300
- Completed retest runs: 300

Missing-data rule: accuracy denominators are analysable runs (completed, graded, eligible case). Unavailable, failed, pending and withdrawn runs are never counted as incorrect; they are reported here. Paired comparisons use cases analysable in BOTH conditions. Mixed models use all analysable main runs (likelihood-based; valid if missingness depends only on modelled terms and the case).

## Accuracy by condition (Wilson 95% CI)

| Outcome | Condition | Correct / analysable | Accuracy (95% CI) |
|---|---|---|---|
| dx | Osler / Text only | 210 / 421 | 49.9% (45.1%-54.6%) |
| dx | Osler / Text + image | 205 / 419 | 48.9% (44.2%-53.7%) |
| dx | Sackett / Text only | 212 / 421 | 50.4% (45.6%-55.1%) |
| dx | Sackett / Text + image | 210 / 419 | 50.1% (45.4%-54.9%) |
| dx | Snow / Text only | 234 / 421 | 55.6% (50.8%-60.3%) |
| dx | Snow / Text + image | 239 / 419 | 57.0% (52.3%-61.7%) |
| mgmt | Osler / Text only | 250 / 421 | 59.4% (54.6%-64.0%) |
| mgmt | Osler / Text + image | 249 / 419 | 59.4% (54.7%-64.0%) |
| mgmt | Sackett / Text only | 270 / 421 | 64.1% (59.4%-68.6%) |
| mgmt | Sackett / Text + image | 260 / 419 | 62.1% (57.3%-66.6%) |
| mgmt | Snow / Text only | 270 / 421 | 64.1% (59.4%-68.6%) |
| mgmt | Snow / Text + image | 266 / 419 | 63.5% (58.8%-68.0%) |

## Paired comparisons (exact McNemar; Holm within each family and outcome; Newcombe paired 95% CI)

Families: F1 = text+image vs text within each model (3 tests); F2 = model pairs within text only (3); F3 = model pairs within text+image (3).

| Outcome | Family | Comparison | Pairs | Diff, pp (95% CI) | Holm p |
|---|---|---|---|---|---|
| dx | F1_input_within_model | Osler / Text + image vs Osler / Text only | 419 | -1.2 (-6.9 to 4.5) | 1 |
| dx | F1_input_within_model | Sackett / Text + image vs Sackett / Text only | 419 | 0.0 (-5.8 to 5.8) | 1 |
| dx | F1_input_within_model | Snow / Text + image vs Snow / Text only | 419 | 1.4 (-4.4 to 7.2) | 1 |
| dx | F2_model_within_text | Sackett / Text only vs Osler / Text only | 421 | 0.5 (-5.5 to 6.5) | 0.939 |
| dx | F2_model_within_text | Snow / Text only vs Osler / Text only | 421 | 5.7 (-0.2 to 11.6) | 0.217 |
| dx | F2_model_within_text | Snow / Text only vs Sackett / Text only | 421 | 5.2 (-0.6 to 11.0) | 0.217 |
| dx | F3_model_within_image | Sackett / Text + image vs Osler / Text + image | 419 | 1.2 (-4.8 to 7.2) | 0.757 |
| dx | F3_model_within_image | Snow / Text + image vs Osler / Text + image | 419 | 8.1 (2.6 to 13.5) | 0.0153 |
| dx | F3_model_within_image | Snow / Text + image vs Sackett / Text + image | 419 | 6.9 (1.1 to 12.6) | 0.0484 |
| mgmt | F1_input_within_model | Osler / Text + image vs Osler / Text only | 419 | 0.0 (-5.9 to 5.9) | 1 |
| mgmt | F1_input_within_model | Sackett / Text + image vs Sackett / Text only | 419 | -1.9 (-8.0 to 4.2) | 1 |
| mgmt | F1_input_within_model | Snow / Text + image vs Snow / Text only | 419 | -0.7 (-6.4 to 5.0) | 1 |
| mgmt | F2_model_within_text | Sackett / Text only vs Osler / Text only | 421 | 4.8 (-1.3 to 10.7) | 0.398 |
| mgmt | F2_model_within_text | Snow / Text only vs Osler / Text only | 421 | 4.8 (-1.1 to 10.6) | 0.398 |
| mgmt | F2_model_within_text | Snow / Text only vs Sackett / Text only | 421 | 0.0 (-6.0 to 6.0) | 1 |
| mgmt | F3_model_within_image | Sackett / Text + image vs Osler / Text + image | 419 | 2.6 (-3.4 to 8.6) | 0.873 |
| mgmt | F3_model_within_image | Snow / Text + image vs Osler / Text + image | 419 | 4.1 (-1.8 to 9.9) | 0.613 |
| mgmt | F3_model_within_image | Snow / Text + image vs Sackett / Text + image | 419 | 1.4 (-4.4 to 7.2) | 0.873 |

## Mixed-effects logistic regression - Diagnostic accuracy

`y ~ model * input + subspecialty_covariate + (1 | case_id)`; 2520 runs, 421 cases; case random-intercept SD = 1.26. Reference: Osler, text only, largest subspecialty.

Model diagnostics: no convergence, singularity or separation warnings.

| LRT | Chi-sq | df | p |
|---|---|---|---|
| interaction | 0.35 | 2 | 0.84 |
| model_overall | 13.11 | 4 | 0.0107 |
| input_overall | 0.35 | 3 | 0.95 |

Model-based simple effects (odds ratios for a typical case, subspecialty-weighted; Holm within family):

| Family | Within | Contrast | OR (95% CI) | Holm p |
|---|---|---|---|---|
| F1_input_within_model | Osler | Text + image vs Text only | 0.95 (0.70-1.29) | 1 |
| F1_input_within_model | Sackett | Text + image vs Text only | 0.99 (0.73-1.34) | 1 |
| F1_input_within_model | Snow | Text + image vs Text only | 1.08 (0.79-1.48) | 1 |
| F2_model_within_text | text_only | Sackett / Osler | 1.03 (0.75-1.40) | 0.872 |
| F2_model_within_text | text_only | Snow / Osler | 1.36 (1.00-1.85) | 0.16 |
| F2_model_within_text | text_only | Snow / Sackett | 1.32 (0.97-1.80) | 0.16 |
| F3_model_within_image | text_image | Sackett / Osler | 1.07 (0.78-1.45) | 0.686 |
| F3_model_within_image | text_image | Snow / Osler | 1.54 (1.13-2.11) | 0.0183 |
| F3_model_within_image | text_image | Snow / Sackett | 1.45 (1.06-1.98) | 0.0383 |

Adjusted accuracy = model-predicted accuracy averaged over the analysed cases and over the case random effect (population-averaged, standardised to the benchmark case mix):

- Osler text_image: 49.0% (44.2%-53.7%)
- Osler text_only: 50.0% (45.5%-54.7%)
- Sackett text_image: 50.2% (45.5%-54.9%)
- Sackett text_only: 50.5% (45.9%-55.1%)
- Snow text_image: 57.3% (52.5%-61.8%)
- Snow text_only: 55.8% (51.1%-60.2%)

## Mixed-effects logistic regression - Management accuracy

`y ~ model * input + subspecialty_covariate + (1 | case_id)`; 2520 runs, 421 cases; case random-intercept SD = 0.93. Reference: Osler, text only, largest subspecialty.

Model diagnostics: no convergence, singularity or separation warnings.

| LRT | Chi-sq | df | p |
|---|---|---|---|
| interaction | 0.26 | 2 | 0.88 |
| model_overall | 5.01 | 4 | 0.286 |
| input_overall | 0.50 | 3 | 0.918 |

Model-based simple effects (odds ratios for a typical case, subspecialty-weighted; Holm within family):

| Family | Within | Contrast | OR (95% CI) | Holm p |
|---|---|---|---|---|
| F1_input_within_model | Osler | Text + image vs Text only | 1.00 (0.74-1.35) | 1 |
| F1_input_within_model | Sackett | Text + image vs Text only | 0.90 (0.66-1.22) | 1 |
| F1_input_within_model | Snow | Text + image vs Text only | 0.97 (0.71-1.31) | 1 |
| F2_model_within_text | text_only | Sackett / Osler | 1.27 (0.94-1.72) | 0.357 |
| F2_model_within_text | text_only | Snow / Osler | 1.27 (0.94-1.72) | 0.357 |
| F2_model_within_text | text_only | Snow / Sackett | 1.00 (0.74-1.36) | 1 |
| F3_model_within_image | text_image | Sackett / Osler | 1.14 (0.84-1.54) | 0.783 |
| F3_model_within_image | text_image | Snow / Osler | 1.23 (0.91-1.66) | 0.553 |
| F3_model_within_image | text_image | Snow / Sackett | 1.08 (0.79-1.46) | 0.783 |

Adjusted accuracy = model-predicted accuracy averaged over the analysed cases and over the case random effect (population-averaged, standardised to the benchmark case mix):

- Osler text_image: 59.5% (54.5%-64.1%)
- Osler text_only: 59.4% (54.9%-64.0%)
- Sackett text_image: 62.1% (57.4%-66.6%)
- Sackett text_only: 64.2% (59.6%-68.5%)
- Snow text_image: 63.6% (58.8%-68.0%)
- Snow text_only: 64.2% (59.7%-68.4%)

## Source-retrieval sensitivity analyses

- S1_exclude_confirmed_retrieval: 58 cases removed (348 main runs); 363 cases remain. Excludes every case in which ANY main-condition run cited the source case.
- S2_also_exclude_incomplete_assessment: 58 cases removed (348 main runs); 363 cases remain. Also excludes cases with any missing/Unclear retrieval assessment (worst case).
- S3_complete_cases_dx: 2 cases removed (NA main runs); 419 cases remain. Cases analysable in all six main conditions
- S3_complete_cases_mgmt: 2 cases removed (NA main runs); 419 cases remain. Cases analysable in all six main conditions
- Cases with incomplete/Unclear retrieval assessment: 0. A missing source citation does not prove the model did not use the source.

## Secondary analyses (see tables/)

- T5 conditional management accuracy: descriptive association only; not a causal effect of a correct diagnosis.
- T6 subspecialty: descriptive; groups < 20 cases not tested.
- T7 imaging modality: exploratory, cases with several modalities count in each.
- T8 partial correctness (lenient scoring), T9 image interpretation, T10 duration/citations (median, IQR), T11 retrieval rates.
- T12 inter-grader agreement (pre-adjudication): diagnosis kappa 0.82 (n=2820), management kappa 0.98 (n=2820).
- T13 test-retest agreement per condition and outcome.
- T14 historical comparison: DESCRIPTIVE ONLY. The 2026 model can no longer be run; differences mix model change, platform change and prompt changes (title removed, answer-format line added, full-length text).

