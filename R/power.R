#!/usr/bin/env Rscript
# =============================================================================
# Power / minimum detectable difference for the paired McNemar comparisons.
#   Rscript R/power.R [pilot_data_root] [output_dir]
# Without a pilot root, an assumption grid is produced. With one, observed
# discordance from the pilot (main runs) is summarised with 95% CIs and the
# upper CI bound is used as the conservative planning value.
#
# Assumptions (state them in the protocol):
#  * Target: one pairwise comparison of two conditions on the same cases
#    (e.g. Snow text+image vs Snow text only), two-sided exact McNemar test.
#  * Multiplicity: Holm within a 3-test family. The first (smallest-p) test is
#    judged at alpha/3 = 0.0167, the second at 0.025, the third at 0.05.
#    Planning at 0.0167 is conservative for the family's first rejection.
#  * Discordance = proportion of cases where the two conditions disagree. It
#    drives power more than accuracy itself and is unknown until the pilot.
#  * n = paired, analysable cases (421 if all are complete; fewer after
#    unavailable images or the source-retrieval sensitivity exclusion).
# =============================================================================
source(file.path("R", "functions.R"))
args <- commandArgs(trailingOnly = TRUE)
pilot <- if (length(args) >= 1 && nzchar(args[1]) && args[1] != "none") args[1] else NULL
out <- if (length(args) >= 2) args[2] else file.path("outputs", "power")
dir.create(out, recursive = TRUE, showWarnings = FALSE)

grid <- expand.grid(n_pairs = c(421, 380, 340), discordance = c(0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40),
                    alpha = c(0.05, 0.025, 0.05 / 3))
grid$min_detectable_diff_pp <- 100 * mapply(min_detectable_diff, grid$n_pairs, grid$discordance, grid$alpha)
grid$power_at_6pp <- mapply(function(n, pd, a) mcnemar_power(n, (pd + 0.06) / 2, (pd - 0.06) / 2, a), grid$n_pairs, grid$discordance, grid$alpha)
grid$power_at_8pp <- mapply(function(n, pd, a) mcnemar_power(n, (pd + 0.08) / 2, (pd - 0.08) / 2, a), grid$n_pairs, grid$discordance, grid$alpha)
write.csv(grid, file.path(out, "power_grid_mcnemar.csv"), row.names = FALSE)

lines <- c("# Power calculation - paired exact McNemar test (assumption grid)", "",
           "These are planning calculations from stated assumptions, not study results.", "",
           "Minimum detectable absolute difference (percentage points) at 80% power, n = 421 paired cases:", "",
           "| Discordance | alpha 0.05 | alpha 0.025 (Holm 2nd) | alpha 0.0167 (Holm 1st of 3) |", "|---|---|---|---|")
for (pd in unique(grid$discordance)) {
  g <- grid[grid$n_pairs == 421 & grid$discordance == pd, ]
  lines <- c(lines, sprintf("| %.0f%% | %.1f | %.1f | %.1f |", 100 * pd, g$min_detectable_diff_pp[g$alpha == 0.05],
                            g$min_detectable_diff_pp[g$alpha == 0.025], g$min_detectable_diff_pp[abs(g$alpha - 0.05 / 3) < 1e-9]))
}
lines <- c(lines, "", "Interpretation: at n = 421 the methodology's '6-8 percentage points' corresponds to discordance of roughly 15-30% at alpha 0.05, and roughly 15-25% at the Holm first-step alpha of 0.0167. With 35-40% discordance the detectable difference is about 9-10 points, and it grows further when fewer pairs are analysable (see the n = 380 and 340 rows). It is therefore a plausible but unverified figure until pilot discordance is known.", "",
           "Full grid (n = 421, 380, 340): power_grid_mcnemar.csv")

if (!is.null(pilot)) {
  cfg <- jsonlite::fromJSON(file.path("config", "study_config.json"), simplifyVector = FALSE)
  families <- lapply(cfg$analysis$comparison_families, function(f) lapply(f, unlist))
  d <- read_analysis(pilot)
  pt <- rbind(paired_family_tests(d, "dx", families), paired_family_tests(d, "mgmt", families))
  disc <- pt[, c("outcome", "family", "comparison", "paired_cases", "A_only", "B_only", "discordance")]
  ci <- wilson_ci(disc$A_only + disc$B_only, disc$paired_cases)
  disc$disc_lower <- ci[, 1]; disc$disc_upper <- ci[, 2]
  disc$mdd_pp_at_upper_alpha0167 <- 100 * sapply(disc$disc_upper, function(p) min_detectable_diff(421, p, 0.05 / 3))
  if (any(d$synthetic)) disc <- cbind(data_status = "SYNTHETIC - NOT STUDY DATA", disc)
  write.csv(disc, file.path(out, "pilot_discordance.csv"), row.names = FALSE)
  lines <- c(lines, "", "## Pilot-informed planning", "",
             sprintf("Pilot paired cases per comparison: %s. With ~10 pilot cases the discordance CI is very wide; the upper bound is used.",
                     paste(unique(disc$paired_cases), collapse = ", ")),
             if (any(d$synthetic)) "**Pilot root is SYNTHETIC - numbers are for demonstration only.**" else NULL,
             "", "See pilot_discordance.csv.")
}
writeLines(lines, file.path(out, "power_report.md"))
cat(paste(lines, collapse = "\n"), "\n")
