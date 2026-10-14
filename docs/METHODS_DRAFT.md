# Methods (draft)

*This draft describes only the workflow as implemented. Text in [square
brackets] depends on an open or provisional decision (docs/DECISION_LOG.md) and
must be confirmed or rewritten before submission. No results are reported.*

## Design

We performed a 3 × 2 within-case factorial evaluation. Each eligible case was
presented under six conditions: three OpenEvidence models (Osler, Sackett and
Snow, [as listed in the model selector on <date>]) crossed with two input
formats (text only; text with images). Every case therefore served as its own
control. [Darwin, offered by application only, was not evaluated.]

## Cases

The benchmark was the same set of 422 JAMA Ophthalmology Clinical Challenges
used in our 2026 evaluation, with the same 10-group subspecialty classification.
One case (case 234) was excluded, as in 2026, [because <reason>], leaving 421
eligible cases. For each case we recorded subspecialty, publication year,
number of figures, and the imaging modality of each figure; a case could have
more than one modality. Cases whose figures could not be uploaded (for example,
video-only content) remained eligible. They were run in the text-only
conditions, and their image conditions were recorded as unavailable rather than
incorrect.

## Inputs

*Text-only input.* The narrative vignette, including the published written
figure descriptions, followed by the question "What would you do next?" and the
four published answer options, verbatim and in their published order.

*Image input (substitution).* The figures replaced the written figure
descriptions: legends were removed and the published images were attached. Any
non-visual information in a legend (for example, age, laterality or timing) was
moved into the vignette by [two] reviewers. [Narrative sentences that cite a
figure were retained, with the citation shown as "(Figure N attached)".] This
contrast therefore compares two ways of conveying visual information, written
descriptions versus images. It does not estimate the effect of adding images to
otherwise identical text.

*Images.* Each published figure was uploaded at the highest available
resolution, as a whole figure unless an upload limit required splitting it.
Panel letters, captions and text labels naming a diagnosis were cropped;
arrows and arrowheads were kept. File names were neutral (`IMG-<case>-<n>`).
The same image files were used for all three models, which we verified by
comparing uploaded image identifiers across conditions. We recorded the number
of images uploaded and any upload limit. Original images were preserved, and
the preparation steps for each file were documented.

*Prompt.* Prompts were generated deterministically from the approved case text
and a locked prompt version, and each prompt was fingerprinted (SHA-256). The
collection prompt [P1] used the 2026 instruction prefix (expert role, plan,
step-by-step reasoning), with the reference to the case title removed because
titles were no longer shown. The image prefix stated that the figures were
attached. A fixed answer-format line was added: "Begin your response with two
lines: 'Diagnosis: <single most likely diagnosis>' and 'Next step: <letter>'".
[No instruction to avoid the source article was given.] Case titles, reference
answers and article discussions were never included in any input.

*Comparability with 2026.* The text-only Osler condition is the closest
successor to the 2026 evaluation, but it is not an exact replication. Case
titles were removed. The answer-format line was added. Eleven cases that had
been shortened in 2026 to fit a character limit were presented in full. In the
stored 2026 prompts, the instruction prefix was absent for 151 of 422 cases
[whether it was entered at run time cannot be verified]. The 2026 model can no
longer be run. Comparisons with 2026 are therefore descriptive only.

## Randomization and schedule

The order of the six conditions was randomized within each case (Python
`random.Random`, seed 20261002; one shuffle per case in case-ID order). A
retest subset of 50 eligible cases was selected with seed 2026. The retest
condition order continued the same random stream. The schedule (2,526 main and
300 retest runs) can be regenerated exactly from these seeds. Retests were
scheduled at least 7 days after the matching main run.

## Data collection

Runs were entered by hand through the OpenEvidence web interface from a verified
clinician account. Each run used a new chat with no prior history [and memory or
personalization disabled]. The model was selected and confirmed before
submission. Image files were attached in the same message as the text. For each
attempt we logged the collector, prompt version and fingerprint, date, time and
timezone, response duration, image identifiers, full response, screenshot and
number of citations. [Collectors were assigned whole cases, so that each
collector entered all six conditions of a case.]

Runs that failed for technical reasons or a protocol deviation were retried.
Failed attempts were retained, and the first completed attempt was analysed. No
run was repeated because of its answer.

## Contamination assessment

For every response, a reviewer checked whether any citation was the source
Clinical Challenge, its answer discussion, or a case report of the same patient
(Yes / No / Unclear). Retrieval rates are reported by condition.

## Grading

Responses were assigned random neutral identifiers. Two graders scored every
response independently, from packets without model, input, condition, run type
or timing information. Each grader received an independently ordered packet
and could not see the other's scores. The machine-parsed answer lines were
shown as a starting point, and graders confirmed them against the full
response.

*Diagnosis:* only the first-listed diagnosis was scored. It was correct if it
matched the published diagnosis or an accepted synonym written before grading.
Partially correct answers (right category, wrong entity) were scored incorrect
and recorded separately.

*Management:* correct if the selected option matched the published answer.
Responses selecting several options or none were scored incorrect.

Disagreements on either outcome were resolved by a third reviewer.
Pre-adjudication scores were kept for agreement statistics. In image
conditions, graders also rated the description of image findings [Correct /
Partly correct / Incorrect / Invented findings / Not described]. This rating
could not be blinded to input.

## Statistical analysis

Analyses were performed separately for diagnostic and management correctness,
in R [version] with lme4 and emmeans. Accuracy for each condition is reported
with Wilson 95% confidence intervals. Denominators are runs that were completed
and graded for eligible cases. Unavailable, failed or withdrawn runs were not
counted as incorrect and are reported in a run-flow table.

The primary model was a mixed-effects logistic regression on main runs:
correct ~ model × input + subspecialty + (1 | case). Osler and text-only were
the reference levels. Subspecialties with fewer than 20 cases [were pooled into
one level for this model]. We report likelihood-ratio tests for the
model-by-input interaction (2 df), for any model effect (model and interaction
terms, 4 df) and for any input effect (3 df); fixed-effect odds ratios with
Wald 95% CIs; and model-based simple-effect odds ratios. Adjusted accuracy is
defined as the model-predicted probability of a correct answer, averaged over
the distribution of the case random effect and over the observed cases. CIs for
adjusted accuracy were obtained by simulating 2,000 fixed-effect vectors from
their estimated sampling distribution. Convergence, singular fits, possible
separation and sparse cells were checked and reported. The planned model was
not replaced.

Paired comparisons used exact McNemar tests on cases analysable in both
conditions, with Holm correction within three pre-specified families per
outcome. F1: text plus images versus text only within each model. F2: pairwise
model comparisons within text only. F3: pairwise model comparisons within text
plus images. Absolute paired differences are given in percentage points with
Newcombe (method 10) 95% CIs.

*Sensitivity analyses:* (S1) excluding every case in which any main-condition
run cited the source case; (S2) additionally excluding cases with a missing or
unclear retrieval assessment; (S3) cases analysable in all six conditions. The
numbers of cases and runs removed are reported. Absence of a source citation
does not exclude contamination.

*Secondary and exploratory analyses:* management accuracy conditional on
diagnostic correctness (descriptive association, not a causal effect);
subspecialty accuracy (descriptive; groups with fewer than 20 cases not
tested) and the Spearman correlation between diagnostic and management accuracy
across subspecialties; paired image-minus-text differences by imaging modality
(a case counted in each of its modalities); lenient diagnostic accuracy counting
partial answers as correct; image-interpretation categories; median (IQR)
response duration and citation count; Cohen's kappa between graders for each
outcome (pre-adjudication); and test–retest agreement (kappa) for each condition
and outcome on the 50-case subset. Retest runs were excluded from all other
analyses.

*Sample size:* with 421 paired cases, an exact McNemar test at 80% power detects
absolute differences of about 6.5–7.8 percentage points at 20–30% discordance
(α = 0.05), and 7.3–9.0 points at the Holm first-step α of 0.0167. [Pilot
discordance: …]
