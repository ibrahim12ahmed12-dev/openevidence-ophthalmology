# R tests. Run from repo root:  Rscript tests/R/test_functions.R
# All data are SYNTHETIC toy inputs or the synthetic demo root.
suppressPackageStartupMessages(library(testthat))
source(file.path("R", "functions.R"))

test_that("Wilson CI matches the workbook cached 2026 interval (200/421; workbook uses z = 1.96)", {
  ci <- wilson_ci(200, 421)
  expect_equal(ci[1], 0.4277977142, tolerance = 1e-5)
  expect_equal(ci[2], 0.5227720982, tolerance = 1e-5)
  expect_true(all(is.na(wilson_ci(0, 0))))
})

test_that("Newcombe paired CI behaves", {
  ci <- newcombe_paired(30, 10, 10, 50)
  expect_equal(unname(ci["diff"]), 0)
  expect_lt(ci["lower"], 0); expect_gt(ci["upper"], 0)
  ci2 <- newcombe_paired(30, 25, 5, 40)
  expect_equal(unname(ci2["diff"]), 0.2)
  expect_true(ci2["lower"] > 0 && ci2["upper"] < 1 && ci2["lower"] < 0.2 && ci2["upper"] > 0.2)
  # close to Wald for large samples
  n <- 4000; ci3 <- newcombe_paired(1200, 800, 400, 1600)
  wald_se <- sqrt(((800 + 400) / n - ((800 - 400) / n)^2) / n)
  expect_equal(unname(ci3["upper"] - ci3["lower"]), 2 * 1.96 * wald_se, tolerance = 0.01)
  # all-correct edge case does not error
  expect_true(is.finite(newcombe_paired(10, 0, 0, 0)["lower"]))
})

test_that("Exact McNemar", {
  expect_equal(mcnemar_exact(10, 0), 2 * 0.5^10)
  expect_equal(mcnemar_exact(0, 0), 1)
  expect_equal(mcnemar_exact(7, 7), 1)
})

test_that("Cohen's kappa hand example", {
  k <- cohen_kappa(c(1, 1, 0, 0), c(1, 0, 0, 0))
  expect_equal(unname(k["agree"]), 0.75)
  expect_equal(unname(k["kappa"]), 0.5)
  expect_true(is.na(cohen_kappa(c(1, 1), c(1, 1))["kappa"]))
})

test_that("McNemar power: size under H0 and monotone in difference", {
  expect_lte(mcnemar_power(421, 0.1, 0.1, 0.05), 0.05)
  p1 <- mcnemar_power(421, 0.13, 0.07); p2 <- mcnemar_power(421, 0.15, 0.05)
  expect_gt(p2, p1)
  expect_equal(min_detectable_diff(421, 0.20, 0.05) > 0.05 & min_detectable_diff(421, 0.20, 0.05) < 0.08, TRUE)
})

# toy long dataset: 4 cases x 6 conditions, main + retest -------------------
toy <- function() {
  g <- expand.grid(case_id = 1:4, condition = 1:6)
  g$run_type <- "Main"; g$eligible <- "Yes"; g$run_status <- "completed"
  g$model <- factor(MODELS[(g$condition + 1) %/% 2], MODELS)
  g$input <- factor(INPUTS[2 - g$condition %% 2], INPUTS)
  g$dx_final <- as.numeric(g$case_id <= 2 | g$condition == 6)
  g$mgmt_final <- 1; g$analyzable_dx <- 1; g$analyzable_mgmt <- 1
  g$source_retrieved <- "No"; g$run_id <- paste0(g$case_id, "-C", g$condition)
  g$subspecialty <- "A"; g$subspecialty_covariate <- "A"; g$synthetic <- TRUE
  g
}

test_that("Unavailable runs leave denominators, never count as incorrect", {
  d <- toy()
  d$run_status[d$case_id == 1 & d$condition == 2] <- "unavailable"
  d$analyzable_dx[d$case_id == 1 & d$condition == 2] <- 0
  d$dx_final[d$case_id == 1 & d$condition == 2] <- NA
  a <- accuracy_by_condition(d, "dx")
  expect_equal(a$denominator[a$condition == 2], 3)
  expect_equal(a$unavailable[a$condition == 2], 1)
  pt <- pair_table(d, "dx", 2, 1)
  expect_equal(pt$n, 3)  # pairing preserved: case 1 dropped from this comparison only
})

test_that("Retrieval sensitivity removes whole cases, uses main runs only", {
  d <- toy()
  d$source_retrieved[d$case_id == 3 & d$condition == 5] <- "Yes"
  r <- d[d$case_id == 4 & d$condition == 1, ]; r$run_type <- "Retest"; r$source_retrieved <- "Yes"
  d <- rbind(d, r)
  d$source_retrieved[d$case_id == 2 & d$condition == 1] <- NA
  s <- sensitivity_sets(d)
  expect_equal(sort(s$S1_exclude_confirmed_retrieval$cases), c(1, 2, 4))
  expect_equal(s$S1_exclude_confirmed_retrieval$removed_runs, 6)
  expect_equal(sort(s$S2_also_exclude_incomplete_assessment$cases), c(1, 4))
})

test_that("Holm applied within each family", {
  d <- toy()
  fam <- list(F1 = list(c(2, 1), c(4, 3), c(6, 5)), F2 = list(c(3, 1)))
  pt <- paired_family_tests(d, "dx", fam)
  f1 <- pt[pt$family == "F1", ]
  expect_equal(f1$p_holm, p.adjust(f1$p_mcnemar_exact, "holm"))
  expect_equal(pt$p_holm[pt$family == "F2"], pt$p_mcnemar_exact[pt$family == "F2"])
  expect_equal(f1$diff_pp[3], 50)
})

test_that("Primary GLMM fits on the synthetic demo and returns checks", {
  root <- file.path("synthetic", "demo_data")
  skip_if_not(file.exists(file.path(root, "analysis", "analysis_dataset.csv")))
  d <- read_analysis(root)
  expect_true(is_synthetic(d))
  pf <- fit_primary(d, "dx")
  expect_false(inherits(pf$fit, "error"))
  ck <- model_checks(pf)
  expect_equal(ck$n_cases, 421)
  expect_true(ck$n_runs <= 2526)
  lr <- lrt_tests(pf)
  expect_equal(lr$df, c(2, 4, 3))
  aa <- adjusted_accuracy(pf, ndraw = 200)
  expect_equal(nrow(aa$cells), 6)
  expect_true(all(aa$cells$lower <= aa$cells$adjusted_accuracy & aa$cells$adjusted_accuracy <= aa$cells$upper))
  tr <- test_retest(d)
  expect_equal(nrow(tr), 12)
  expect_true(all(tr$pairs <= 50))
})

cat("All R tests finished.\n")
