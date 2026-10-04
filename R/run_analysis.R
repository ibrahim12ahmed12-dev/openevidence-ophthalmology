#!/usr/bin/env Rscript
# =============================================================================
# Main analysis. Usage (from the repository root):
#   Rscript R/run_analysis.R [data_root] [output_dir]
# Defaults: data_root = data, output_dir = outputs
# Synthetic demo: Rscript R/run_analysis.R synthetic/demo_data synthetic/demo_outputs
#
# Primary model per outcome (main runs only, eligible cases, analysable runs):
#   correct ~ model * input + subspecialty_covariate + (1 | case_id)
# Retests are analysed separately (test-retest agreement only).
# =============================================================================
suppressPackageStartupMessages({
  source(file.path("R", "check_packages.R"))
  check_packages(c("lme4", "emmeans", "jsonlite", "ggplot2"))
  source(file.path("R", "functions.R"))
  source(file.path("R", "figures.R"))
})

args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args) >= 1) args[1] else "data"
out <- if (length(args) >= 2) args[2] else "outputs"
dir.create(file.path(out, "tables"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(out, "figures"), recursive = TRUE, showWarnings = FALSE)

cfg <- jsonlite::fromJSON(file.path("config", "study_config.json"), simplifyVector = FALSE)
d <- read_analysis(root)
SYN <- is_synthetic(d)
BANNER <- if (SYN) "SYNTHETIC DEMONSTRATION - NOT STUDY RESULTS" else ""
families <- lapply(cfg$analysis$comparison_families, function(f) lapply(f, unlist))

wt <- function(x, name) {
  if (is.null(x)) return(invisible(NULL))
  if (SYN) x <- cbind(data_status = "SYNTHETIC - NOT STUDY DATA", x)
  write.csv(x, file.path(out, "tables", paste0(name, ".csv")), row.names = FALSE, na = "")
}
md <- c(if (SYN) c(paste("#", BANNER), "", "Every number below comes from randomly generated data and says nothing about OpenEvidence.", "") else NULL,
        "# Analysis report", "", paste("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M %Z"), "| data root:", root), "")
fmtp <- function(x) ifelse(is.na(x), "NA", sprintf("%.1f%%", 100 * x))

# ------------------------------------------------------------------ 0. flow
main <- d[d$run_type == "Main", ]
flow <- data.frame(
  item = c("Scheduled main runs", "  of which eligible cases", "Completed", "Unavailable (e.g. image cannot be uploaded)",
           "Failed without completed retry", "Pending", "Withdrawn", "Analysable - diagnosis", "Analysable - management",
           "Scheduled retest runs", "Completed retest runs"),
  n = c(nrow(main), sum(main$eligible == "Yes"), sum(main$run_status == "completed"), sum(main$run_status == "unavailable"),
        sum(main$run_status == "failed"), sum(main$run_status == "pending"), sum(main$run_status == "withdrawn"),
        sum(main$analyzable_dx == 1), sum(main$analyzable_mgmt == 1),
        sum(d$run_type == "Retest"), sum(d$run_type == "Retest" & d$run_status == "completed")))
wt(flow, "T0_run_flow")
md <- c(md, "## Run flow", "", paste0("- ", flow$item, ": ", flow$n), "",
        "Missing-data rule: accuracy denominators are analysable runs (completed, graded, eligible case). Unavailable, failed, pending and withdrawn runs are never counted as incorrect; they are reported here. Paired comparisons use cases analysable in BOTH conditions. Mixed models use all analysable main runs (likelihood-based; valid if missingness depends only on modelled terms and the case).", "")

# ------------------------------------------------------------------ 1. accuracy
acc <- rbind(accuracy_by_condition(d, "dx"), accuracy_by_condition(d, "mgmt"))
wt(acc, "T1_accuracy_by_condition")
md <- c(md, "## Accuracy by condition (Wilson 95% CI)", "", "| Outcome | Condition | Correct / analysable | Accuracy (95% CI) |", "|---|---|---|---|",
        sprintf("| %s | %s | %d / %d | %s (%s-%s) |", acc$outcome, acc$label, acc$correct, acc$denominator,
                fmtp(acc$accuracy), fmtp(acc$ci_lower), fmtp(acc$ci_upper)), "")

# ------------------------------------------------------------------ 2. paired tests
pt <- rbind(paired_family_tests(d, "dx", families), paired_family_tests(d, "mgmt", families))
wt(pt, "T2_paired_mcnemar_holm")
md <- c(md, "## Paired comparisons (exact McNemar; Holm within each family and outcome; Newcombe paired 95% CI)", "",
        "Families: F1 = text+image vs text within each model (3 tests); F2 = model pairs within text only (3); F3 = model pairs within text+image (3).", "",
        "| Outcome | Family | Comparison | Pairs | Diff, pp (95% CI) | Holm p |", "|---|---|---|---|---|---|",
        sprintf("| %s | %s | %s | %d | %.1f (%.1f to %.1f) | %.3g |", pt$outcome, pt$family, pt$comparison, pt$paired_cases,
                pt$diff_pp, pt$diff_lower_pp, pt$diff_upper_pp, pt$p_holm), "")

# ------------------------------------------------------------------ 3. mixed models
checks_txt <- character(0)
for (o in c("dx", "mgmt")) {
  pf <- fit_primary(d, o)
  ck <- model_checks(pf)
  checks_txt <- c(checks_txt, paste0("=== ", o, " ==="), capture.output(str(ck[setdiff(names(ck), "sparse_cells")])),
                  "Sparse / all-same cells (n<5 or 0% or 100%):", capture.output(print(ck$sparse_cells, row.names = FALSE)), "")
  if (inherits(pf$fit, "error")) {
    md <- c(md, paste0("## Mixed model - ", o), "", paste("**Model did not fit:**", ck$status, "- reported, not replaced."), "")
    next
  }
  lr <- lrt_tests(pf); or <- odds_ratios(pf); se <- simple_effects(pf); aa <- adjusted_accuracy(pf)
  wt(lr, paste0("T3_", o, "_lrt")); wt(or, paste0("T3_", o, "_odds_ratios")); wt(se, paste0("T3_", o, "_simple_effects"))
  wt(aa$cells, paste0("T3_", o, "_adjusted_accuracy")); wt(aa$input_differences, paste0("T3_", o, "_adjusted_input_differences"))
  probs <- c(if (length(ck$warnings)) paste("warnings:", paste(ck$warnings, collapse = " | ")),
             if (isTRUE(ck$singular)) "singular fit (random-intercept variance ~ 0)",
             if (length(ck$conv_messages)) paste("convergence:", paste(ck$conv_messages, collapse = " | ")),
             if (length(ck$possible_separation_terms)) paste("possible separation in:", paste(ck$possible_separation_terms, collapse = ", ")),
             if (length(ck$covariate_levels_all_same_outcome)) paste("covariate levels with all-same outcome:", paste(ck$covariate_levels_all_same_outcome, collapse = ", ")))
  md <- c(md, paste0("## Mixed-effects logistic regression - ", OUTCOME_LABEL[[o]]), "",
          paste0("`", ck$formula, "`; ", ck$n_runs, " runs, ", ck$n_cases, " cases; case random-intercept SD = ",
                 sprintf("%.2f", ck$random_intercept_sd), ". Reference: Osler, text only, largest subspecialty."), "",
          paste0("Model diagnostics: ", if (length(probs)) paste(probs, collapse = "; ") else "no convergence, singularity or separation warnings."), "",
          "| LRT | Chi-sq | df | p |", "|---|---|---|---|",
          sprintf("| %s | %.2f | %d | %.3g |", lr$test, lr$chisq, lr$df, lr$p_value), "",
          "Model-based simple effects (odds ratios for a typical case, subspecialty-weighted; Holm within family):", "",
          "| Family | Within | Contrast | OR (95% CI) | Holm p |", "|---|---|---|---|---|",
          sprintf("| %s | %s | %s | %.2f (%.2f-%.2f) | %.3g |", se$family, se$by, se$contrast, se$odds_ratio, se$or_lower, se$or_upper, se$p_holm), "",
          "Adjusted accuracy = model-predicted accuracy averaged over the analysed cases and over the case random effect (population-averaged, standardised to the benchmark case mix):", "",
          sprintf("- %s: %s (%s-%s)", aa$cells$cell, fmtp(aa$cells$adjusted_accuracy), fmtp(aa$cells$lower), fmtp(aa$cells$upper)), "")
}
writeLines(checks_txt, file.path(out, "tables", "model_checks.txt"))

# ------------------------------------------------------------------ 4. sensitivity
ss <- sensitivity_sets(d)
sens_rows <- list(); sens_pt <- list()
for (nm in names(ss)) {
  cs <- ss[[nm]]$cases
  dd <- d[d$case_id %in% cs, ]
  a2 <- rbind(accuracy_by_condition(dd, "dx"), accuracy_by_condition(dd, "mgmt")); a2$analysis <- nm
  sens_rows[[nm]] <- a2
  p2 <- rbind(paired_family_tests(dd, "dx", families), paired_family_tests(dd, "mgmt", families)); p2$analysis <- nm
  sens_pt[[nm]] <- p2
  for (o in c("dx", "mgmt")) {
    pf <- fit_primary(dd, o)
    if (!inherits(pf$fit, "error")) wt(lrt_tests(pf), paste0("T4_", nm, "_", o, "_lrt"))
  }
}
cc_rows <- list()
for (o in c("dx", "mgmt")) {
  cc <- complete_case_ids(d, o)
  a3 <- accuracy_by_condition(d[d$case_id %in% cc, ], o); a3$analysis <- "S3_complete_cases_all_six_conditions"
  cc_rows[[o]] <- a3
}
sens_counts <- data.frame(analysis = names(ss), cases_removed = sapply(ss, `[[`, "removed_cases"),
                          main_runs_removed = sapply(ss, `[[`, "removed_runs"), cases_remaining = sapply(ss, function(x) length(x$cases)),
                          rule = sapply(ss, `[[`, "note"))
sens_counts <- rbind(sens_counts, data.frame(analysis = c("S3_complete_cases_dx", "S3_complete_cases_mgmt"),
  cases_removed = length(unique(d$case_id[d$eligible == "Yes"])) - c(length(complete_case_ids(d, "dx")), length(complete_case_ids(d, "mgmt"))),
  main_runs_removed = NA, cases_remaining = c(length(complete_case_ids(d, "dx")), length(complete_case_ids(d, "mgmt"))),
  rule = "Cases analysable in all six main conditions"))
wt(sens_counts, "T4_sensitivity_counts"); wt(do.call(rbind, c(sens_rows, cc_rows)), "T4_sensitivity_accuracy")
wt(do.call(rbind, sens_pt), "T4_sensitivity_paired")
rf <- retrieval_flags(d)
md <- c(md, "## Source-retrieval sensitivity analyses", "",
        sprintf("- %s: %d cases removed (%d main runs); %d cases remain. %s", sens_counts$analysis, sens_counts$cases_removed,
                sens_counts$main_runs_removed, sens_counts$cases_remaining, sens_counts$rule),
        sprintf("- Cases with incomplete/Unclear retrieval assessment: %d. A missing source citation does not prove the model did not use the source.", length(rf$incomplete_cases)), "")

# ------------------------------------------------------------------ 5. secondary
wt(conditional_mgmt(d), "T5_conditional_management")
wt(rbind(subspecialty_table(d, "dx"), subspecialty_table(d, "mgmt")), "T6_subspecialty")
wt(subspecialty_spearman(d), "T6b_subspecialty_spearman")
wt(modality_table(d), "T7_modality_image_effect_exploratory")
wt(partial_table(d), "T8_partial_correct_lenient")
wt(interp_table(d), "T9_image_interpretation")
wt(duration_citations(d), "T10_duration_citations")
rr <- retrieval_rates(d); wt(rr, "T11_retrieval_rates")
ig <- intergrader(d); wt(ig, "T12_intergrader_kappa")
tr <- test_retest(d); wt(tr, "T13_test_retest")
hist <- cfg$historical_2026
hc <- historical_comparison(d, hist); wt(hc, "T14_historical_descriptive")
md <- c(md, "## Secondary analyses (see tables/)", "",
        "- T5 conditional management accuracy: descriptive association only; not a causal effect of a correct diagnosis.",
        "- T6 subspecialty: descriptive; groups < 20 cases not tested.", "- T7 imaging modality: exploratory, cases with several modalities count in each.",
        "- T8 partial correctness (lenient scoring), T9 image interpretation, T10 duration/citations (median, IQR), T11 retrieval rates.",
        sprintf("- T12 inter-grader agreement (pre-adjudication): diagnosis kappa %.2f (n=%d), management kappa %.2f (n=%d).",
                ig$kappa[ig$outcome == "dx" & ig$group == "All"], ig$pairs[ig$outcome == "dx" & ig$group == "All"],
                ig$kappa[ig$outcome == "mgmt" & ig$group == "All"], ig$pairs[ig$outcome == "mgmt" & ig$group == "All"]),
        "- T13 test-retest agreement per condition and outcome.",
        "- T14 historical comparison: DESCRIPTIVE ONLY. The 2026 model can no longer be run; differences mix model change, platform change and prompt changes (title removed, answer-format line added, full-length text).", "")

# ------------------------------------------------------------------ 6. figures
make_figures(acc, pt, rbind(subspecialty_table(d, "dx"), subspecialty_table(d, "mgmt")), rr, file.path(out, "figures"), BANNER)
writeLines(md, file.path(out, "analysis_report.md"))
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
cat("Analysis complete:", file.path(out, "analysis_report.md"), if (SYN) "(SYNTHETIC)" else "", "\n")
