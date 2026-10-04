# =============================================================================
# Statistical functions for the OpenEvidence model-family study.
# Base R except: lme4 (mixed models), emmeans (model-based contrasts).
# Every function returns numerators AND denominators so tables can show them.
# =============================================================================

MODELS <- c("Osler", "Sackett", "Snow")
INPUTS <- c("text_only", "text_image")
INPUT_LABEL <- c(text_only = "Text only", text_image = "Text + image")
COND_LABEL <- c(`1` = "Osler / Text only", `2` = "Osler / Text + image",
                `3` = "Sackett / Text only", `4` = "Sackett / Text + image",
                `5` = "Snow / Text only", `6` = "Snow / Text + image")
OUTCOMES <- c(dx = "dx_final", mgmt = "mgmt_final")
OUTCOME_LABEL <- c(dx = "Diagnostic accuracy", mgmt = "Management accuracy")

# ---------------------------------------------------------------- data access
read_analysis <- function(root) {
  f <- file.path(root, "analysis", "analysis_dataset.csv")
  if (!file.exists(f)) stop("analysis dataset not found: run `python -m oe build-analysis` first (", f, ")")
  d <- read.csv(f, stringsAsFactors = FALSE, na.strings = c(""), colClasses = "character")
  num <- c("case_id", "condition", "run_order", "n_attempts", "response_duration_s", "citation_count",
           "dx_final", "mgmt_final", "partial_final", "dx_g1", "dx_g2", "mgmt_g1", "mgmt_g2",
           "analyzable_dx", "analyzable_mgmt", "elapsed_days_since_main", "publication_year")
  for (v in intersect(num, names(d))) d[[v]] <- suppressWarnings(as.numeric(d[[v]]))
  d$model <- factor(d$model, levels = MODELS)
  d$input <- factor(d$input, levels = INPUTS)
  d$synthetic <- toupper(d$synthetic) == "TRUE"
  d
}

is_synthetic <- function(d) any(d$synthetic)

# outcome-specific analysable main runs among eligible cases
main_runs <- function(d, outcome) {
  a <- paste0("analyzable_", outcome)
  d[d$run_type == "Main" & d$eligible == "Yes" & d[[a]] == 1, ]
}

# ---------------------------------------------------------------- intervals
wilson_ci <- function(x, n, conf = 0.95) {
  z <- qnorm(1 - (1 - conf) / 2)
  out <- t(mapply(function(x, n) {
    if (is.na(n) || n == 0) return(c(NA, NA))
    p <- x / n
    den <- 1 + z^2 / n
    ctr <- (p + z^2 / (2 * n)) / den
    hw <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / den
    c(max(0, ctr - hw), min(1, ctr + hw))
  }, x, n))
  colnames(out) <- c("lower", "upper")
  out
}

# Newcombe (1998) method 10: score-based CI for a difference of paired
# proportions, pA - pB. a = both correct, b = A only, c = B only, d = neither.
newcombe_paired <- function(a, b, c, d, conf = 0.95) {
  n <- a + b + c + d
  if (n == 0) return(c(diff = NA, lower = NA, upper = NA))
  p1 <- (a + b) / n; p2 <- (a + c) / n
  w1 <- wilson_ci(a + b, n, conf); w2 <- wilson_ci(a + c, n, conf)
  l1 <- w1[1]; u1 <- w1[2]; l2 <- w2[1]; u2 <- w2[2]
  den <- sqrt((a + b) * (c + d) * (a + c) * (b + d))
  phi <- if (den == 0) 0 else (a * d - b * c) / den
  D <- p1 - p2
  dl <- sqrt(max(0, (p1 - l1)^2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2)^2))
  du <- sqrt(max(0, (u1 - p1)^2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2)^2))
  c(diff = D, lower = max(-1, D - dl), upper = min(1, D + du))
}

# exact (conditional binomial) McNemar test on discordant counts
mcnemar_exact <- function(b, c) {
  if (b + c == 0) return(1)
  binom.test(b, b + c, 0.5)$p.value
}

# Cohen's kappa for two binary (or categorical) vectors; asymptotic SE (Fleiss, Cohen & Everitt 1969 simple form)
cohen_kappa <- function(x, y, conf = 0.95) {
  ok <- !is.na(x) & !is.na(y)
  x <- x[ok]; y <- y[ok]; n <- length(x)
  if (n == 0) return(c(n = 0, agree = NA, kappa = NA, lower = NA, upper = NA))
  lv <- sort(unique(c(x, y)))
  tab <- table(factor(x, lv), factor(y, lv)) / n
  po <- sum(diag(tab)); pe <- sum(rowSums(tab) * colSums(tab))
  if (isTRUE(all.equal(pe, 1))) return(c(n = n, agree = po, kappa = NA, lower = NA, upper = NA))
  k <- (po - pe) / (1 - pe)
  se <- sqrt(po * (1 - po) / (n * (1 - pe)^2))
  z <- qnorm(1 - (1 - conf) / 2)
  c(n = n, agree = po, kappa = k, lower = k - z * se, upper = min(1, k + z * se))
}

# ---------------------------------------------------------------- descriptive
accuracy_by_condition <- function(d, outcome) {
  m <- main_runs(d, outcome)
  y <- OUTCOMES[[outcome]]
  sched <- d[d$run_type == "Main" & d$eligible == "Yes", ]
  out <- do.call(rbind, lapply(1:6, function(k) {
    s <- sched[sched$condition == k, ]
    mk <- m[m$condition == k, ]
    x <- sum(mk[[y]]); n <- nrow(mk)
    ci <- wilson_ci(x, n)
    data.frame(outcome = outcome, condition = k, label = COND_LABEL[as.character(k)],
               model = MODELS[(k + 1) %/% 2], input = INPUTS[2 - k %% 2],
               scheduled = nrow(s), completed = sum(s$run_status == "completed"),
               unavailable = sum(s$run_status == "unavailable"),
               failed_or_pending = sum(s$run_status %in% c("failed", "pending")),
               withdrawn = sum(s$run_status == "withdrawn"),
               completed_not_graded = sum(s$run_status == "completed") - n,
               correct = x, denominator = n, accuracy = if (n) x / n else NA,
               ci_lower = ci[1], ci_upper = ci[2], stringsAsFactors = FALSE)
  }))
  rownames(out) <- NULL
  out
}

pair_table <- function(d, outcome, ca, cb, cases = NULL) {
  m <- main_runs(d, outcome)
  if (!is.null(cases)) m <- m[m$case_id %in% cases, ]
  y <- OUTCOMES[[outcome]]
  A <- m[m$condition == ca, c("case_id", y)]; B <- m[m$condition == cb, c("case_id", y)]
  names(A)[2] <- "A"; names(B)[2] <- "B"
  mm <- merge(A, B, by = "case_id")
  list(n = nrow(mm), a = sum(mm$A == 1 & mm$B == 1), b = sum(mm$A == 1 & mm$B == 0),
       c = sum(mm$A == 0 & mm$B == 1), d = sum(mm$A == 0 & mm$B == 0),
       n_only_A = nrow(A) - nrow(mm), n_only_B = nrow(B) - nrow(mm))
}

# Paired comparisons with Holm correction WITHIN each family (per outcome).
paired_family_tests <- function(d, outcome, families, cases = NULL) {
  rows <- list()
  for (fam in names(families)) {
    fr <- do.call(rbind, lapply(families[[fam]], function(pr) {
      ca <- pr[1]; cb <- pr[2]
      t <- pair_table(d, outcome, ca, cb, cases)
      ci <- newcombe_paired(t$a, t$b, t$c, t$d)
      data.frame(outcome = outcome, family = fam,
                 comparison = paste0(COND_LABEL[as.character(ca)], " vs ", COND_LABEL[as.character(cb)]),
                 cond_A = ca, cond_B = cb, paired_cases = t$n,
                 unpaired_excluded = t$n_only_A + t$n_only_B,
                 acc_A = if (t$n) (t$a + t$b) / t$n else NA, acc_B = if (t$n) (t$a + t$c) / t$n else NA,
                 both_correct = t$a, A_only = t$b, B_only = t$c, neither = t$d,
                 discordance = if (t$n) (t$b + t$c) / t$n else NA,
                 diff_pp = 100 * ci[["diff"]], diff_lower_pp = 100 * ci[["lower"]], diff_upper_pp = 100 * ci[["upper"]],
                 p_mcnemar_exact = mcnemar_exact(t$b, t$c), stringsAsFactors = FALSE)
    }))
    fr$p_holm <- p.adjust(fr$p_mcnemar_exact, method = "holm")
    rows[[fam]] <- fr
  }
  out <- do.call(rbind, rows); rownames(out) <- NULL
  out
}

# ---------------------------------------------------------------- mixed model
fit_primary <- function(d, outcome, formula_rhs = "model * input + subspecialty_covariate + (1 | case_id)") {
  m <- main_runs(d, outcome)
  m$y <- m[[OUTCOMES[[outcome]]]]
  m$case_id <- factor(m$case_id)
  m$subspecialty_covariate <- factor(m$subspecialty_covariate)
  if (nlevels(m$subspecialty_covariate) > 1) {
    big <- names(sort(table(m$subspecialty_covariate), decreasing = TRUE))[1]
    m$subspecialty_covariate <- relevel(m$subspecialty_covariate, ref = big)
  }
  f <- as.formula(paste("y ~", formula_rhs))
  warn <- character(0)
  fit <- tryCatch(withCallingHandlers(
    lme4::glmer(f, data = m, family = binomial,
                control = lme4::glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))),
    warning = function(w) { warn <<- c(warn, conditionMessage(w)); invokeRestart("muffleWarning") }),
    error = function(e) e)
  list(fit = fit, data = m, warnings = warn, formula = deparse(f), outcome = outcome)
}

model_checks <- function(pf) {
  m <- pf$data; fit <- pf$fit
  chk <- list(outcome = pf$outcome, formula = pf$formula, n_runs = nrow(m), n_cases = length(unique(m$case_id)))
  if (inherits(fit, "error")) {
    chk$status <- paste("FIT FAILED:", conditionMessage(fit))
    return(chk)
  }
  chk$status <- "fitted"
  chk$warnings <- unique(pf$warnings)
  chk$singular <- lme4::isSingular(fit)
  chk$conv_messages <- fit@optinfo$conv$lme4$messages
  chk$random_intercept_sd <- as.numeric(attr(lme4::VarCorr(fit)$case_id, "stddev"))
  co <- summary(fit)$coefficients
  chk$possible_separation_terms <- rownames(co)[abs(co[, 1]) > 8 | co[, 2] > 5]
  # outcome all-0 / all-1 cells
  cells <- aggregate(y ~ subspecialty_covariate + model + input, data = m, FUN = function(v) c(n = length(v), s = sum(v)))
  cells <- data.frame(cells[, 1:3], n = cells$y[, "n"], correct = cells$y[, "s"])
  chk$sparse_cells <- cells[cells$n < 5 | cells$correct == 0 | cells$correct == cells$n, ]
  sub <- aggregate(y ~ subspecialty_covariate, data = m, FUN = function(v) c(n = length(v), s = sum(v)))
  sub <- data.frame(level = sub[, 1], n = sub$y[, "n"], correct = sub$y[, "s"])
  chk$covariate_levels_all_same_outcome <- sub$level[sub$correct == 0 | sub$correct == sub$n]
  chk
}

# Likelihood-ratio tests. Definitions:
#  interaction : full vs (model + input + subspecialty)                    df = 2
#  model overall: full vs (input + subspecialty)  [model + interaction]   df = 4
#  input overall: full vs (model + subspecialty)  [input + interaction]   df = 3
lrt_tests <- function(pf) {
  fit <- pf$fit
  if (inherits(fit, "error")) return(NULL)
  m <- pf$data
  upd <- function(rhs) suppressWarnings(lme4::glmer(as.formula(paste("y ~", rhs)), data = m, family = binomial,
                                                    control = lme4::glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))))
  sub <- if (nlevels(m$subspecialty_covariate) > 1) " + subspecialty_covariate" else ""
  red <- list(interaction = upd(paste0("model + input", sub, " + (1 | case_id)")),
              model_overall = upd(paste0("input", sub, " + (1 | case_id)")),
              input_overall = upd(paste0("model", sub, " + (1 | case_id)")))
  do.call(rbind, lapply(names(red), function(nm) {
    a <- anova(red[[nm]], fit)
    data.frame(outcome = pf$outcome, test = nm, chisq = a$Chisq[2], df = a$Df[2], p_value = a$`Pr(>Chisq)`[2])
  }))
}

odds_ratios <- function(pf) {
  fit <- pf$fit
  if (inherits(fit, "error")) return(NULL)
  co <- summary(fit)$coefficients
  ci <- suppressMessages(confint(fit, method = "Wald", parm = "beta_"))
  data.frame(outcome = pf$outcome, term = rownames(co), log_odds = co[, 1], se = co[, 2],
             odds_ratio = exp(co[, 1]), or_lower = exp(ci[rownames(co), 1]), or_upper = exp(ci[rownames(co), 2]),
             p_wald = co[, 4], row.names = NULL, stringsAsFactors = FALSE)
}

# Simple-effect odds ratios (conditional on a typical case, u = 0), averaged over
# subspecialty with observed-proportion weights. Holm within each family.
simple_effects <- function(pf) {
  fit <- pf$fit
  if (inherits(fit, "error") || !requireNamespace("emmeans", quietly = TRUE)) return(NULL)
  emm1 <- emmeans::emmeans(fit, ~ input | model, weights = "proportional")
  c1 <- summary(emmeans::contrast(emm1, method = list(`Text + image vs Text only` = c(-1, 1))),
                infer = TRUE, type = "response", adjust = "none")
  c1 <- as.data.frame(c1); c1$family <- "F1_input_within_model"; c1$by <- c1$model
  emm2 <- emmeans::emmeans(fit, ~ model | input, weights = "proportional")
  c2 <- as.data.frame(summary(emmeans::contrast(emm2, method = "revpairwise"), infer = TRUE, type = "response", adjust = "none"))
  c2$family <- ifelse(c2$input == "text_only", "F2_model_within_text", "F3_model_within_image"); c2$by <- c2$input
  keep <- function(x) data.frame(outcome = pf$outcome, family = x$family, by = as.character(x$by),
                                 contrast = as.character(x$contrast), odds_ratio = x$odds.ratio,
                                 or_lower = x$asymp.LCL, or_upper = x$asymp.UCL, p_unadjusted = x$p.value)
  out <- rbind(keep(c1), keep(c2))
  out$p_holm <- ave(out$p_unadjusted, out$family, FUN = function(p) p.adjust(p, "holm"))
  out
}

gauss_hermite <- function(n = 30) {
  i <- seq_len(n - 1); J <- matrix(0, n, n)
  J[cbind(i, i + 1)] <- sqrt(i / 2); J[cbind(i + 1, i)] <- sqrt(i / 2)
  e <- eigen(J, symmetric = TRUE)
  list(x = e$values, w = sqrt(pi) * e$vectors[1, ]^2)
}

# Model-based ADJUSTED ACCURACY (definition used in the paper):
# for every analysed case i and condition c, P_ic = E_u[ logit^-1(x_ic'b + u) ],
# u ~ N(0, sigma^2) (integrated numerically), then averaged over the observed
# cases. This is a population-averaged accuracy standardised to the benchmark's
# case mix. CIs: 2000 draws of b from N(b_hat, V_hat), sigma fixed at its estimate.
adjusted_accuracy <- function(pf, ndraw = 2000, seed = 1) {
  fit <- pf$fit
  if (inherits(fit, "error")) return(NULL)
  m <- pf$data
  cases <- unique(m[, c("case_id", "subspecialty_covariate")])
  grid <- merge(cases, expand.grid(model = factor(MODELS, MODELS), input = factor(INPUTS, INPUTS)), by = NULL)
  X <- model.matrix(lme4::nobars(formula(fit))[-2], data = grid)
  b <- lme4::fixef(fit); X <- X[, names(b), drop = FALSE]
  sig <- as.numeric(attr(lme4::VarCorr(fit)$case_id, "stddev"))
  gh <- gauss_hermite(30)
  marg <- function(eta) as.vector(plogis(outer(as.vector(eta), sqrt(2) * sig * gh$x, "+")) %*% (gh$w / sqrt(pi)))
  key <- paste(grid$model, grid$input)
  est <- function(beta) tapply(marg(X %*% beta), key, mean)
  set.seed(seed)
  V <- as.matrix(vcov(fit))
  R <- chol(V)
  draws <- sapply(seq_len(ndraw), function(i) est(b + as.vector(t(R) %*% rnorm(length(b)))))
  point <- est(b)
  res <- data.frame(outcome = pf$outcome, cell = names(point), adjusted_accuracy = as.numeric(point),
                    lower = apply(draws, 1, quantile, 0.025), upper = apply(draws, 1, quantile, 0.975))
  diffs <- do.call(rbind, lapply(MODELS, function(mo) {
    dd <- draws[paste(mo, "text_image"), ] - draws[paste(mo, "text_only"), ]
    data.frame(outcome = pf$outcome, contrast = paste(mo, ": Text + image minus Text only"),
               diff_pp = 100 * (point[paste(mo, "text_image")] - point[paste(mo, "text_only")]),
               lower_pp = 100 * quantile(dd, 0.025), upper_pp = 100 * quantile(dd, 0.975))
  }))
  rownames(res) <- NULL; rownames(diffs) <- NULL
  list(cells = res, input_differences = diffs, sigma = sig, n_cases = nrow(cases))
}

# ---------------------------------------------------------------- sensitivity
retrieval_flags <- function(d) {
  mm <- d[d$run_type == "Main" & d$eligible == "Yes", ]
  comp <- mm[mm$run_status == "completed", ]
  yes <- unique(comp$case_id[!is.na(comp$source_retrieved) & comp$source_retrieved == "Yes"])
  incomplete <- unique(comp$case_id[is.na(comp$source_retrieved) | comp$source_retrieved %in% c("Unclear")])
  list(retrieved_cases = yes, incomplete_cases = setdiff(incomplete, yes))
}

sensitivity_sets <- function(d) {
  rf <- retrieval_flags(d)
  elig <- unique(d$case_id[d$eligible == "Yes"])
  main <- d[d$run_type == "Main" & d$eligible == "Yes", ]
  list(
    S1_exclude_confirmed_retrieval = list(
      cases = setdiff(elig, rf$retrieved_cases),
      removed_cases = length(rf$retrieved_cases),
      removed_runs = sum(main$case_id %in% rf$retrieved_cases),
      note = "Excludes every case in which ANY main-condition run cited the source case."),
    S2_also_exclude_incomplete_assessment = list(
      cases = setdiff(elig, c(rf$retrieved_cases, rf$incomplete_cases)),
      removed_cases = length(union(rf$retrieved_cases, rf$incomplete_cases)),
      removed_runs = sum(main$case_id %in% union(rf$retrieved_cases, rf$incomplete_cases)),
      note = "Also excludes cases with any missing/Unclear retrieval assessment (worst case)."))
}

complete_case_ids <- function(d, outcome) {
  m <- main_runs(d, outcome)
  tab <- table(m$case_id)
  as.numeric(names(tab)[tab == 6])
}

# ---------------------------------------------------------------- secondary
conditional_mgmt <- function(d) {
  m <- main_runs(d, "dx"); m <- m[m$analyzable_mgmt == 1, ]
  do.call(rbind, lapply(1:6, function(k) {
    mk <- m[m$condition == k, ]
    r <- lapply(c(1, 0), function(dxv) {
      s <- mk[mk$dx_final == dxv, ]; x <- sum(s$mgmt_final); n <- nrow(s); ci <- wilson_ci(x, n)
      c(x, n, if (n) x / n else NA, ci)
    })
    data.frame(condition = k, label = COND_LABEL[as.character(k)],
               mgmt_correct_given_dx_correct = r[[1]][1], n_dx_correct = r[[1]][2], acc_given_dx_correct = r[[1]][3],
               lower_1 = r[[1]][4], upper_1 = r[[1]][5],
               mgmt_correct_given_dx_incorrect = r[[2]][1], n_dx_incorrect = r[[2]][2], acc_given_dx_incorrect = r[[2]][3],
               lower_0 = r[[2]][4], upper_0 = r[[2]][5], row.names = NULL)
  }))
}

subspecialty_table <- function(d, outcome, min_n = 20) {
  m <- main_runs(d, outcome); y <- OUTCOMES[[outcome]]
  elig <- unique(d[d$eligible == "Yes", c("case_id", "subspecialty")])
  cnt <- table(elig$subspecialty)
  out <- do.call(rbind, lapply(names(cnt), function(s) do.call(rbind, lapply(1:6, function(k) {
    mk <- m[m$subspecialty == s & m$condition == k, ]; x <- sum(mk[[y]]); n <- nrow(mk); ci <- wilson_ci(x, n)
    data.frame(outcome = outcome, subspecialty = s, eligible_cases = as.integer(cnt[s]), condition = k,
               label = COND_LABEL[as.character(k)], correct = x, denominator = n,
               accuracy = if (n) x / n else NA, ci_lower = ci[1], ci_upper = ci[2],
               reporting = if (cnt[s] < min_n) "descriptive only (<20 cases)" else "descriptive", row.names = NULL)
  }))))
  out[order(-out$eligible_cases, out$subspecialty, out$condition), ]
}

subspecialty_spearman <- function(d, min_n = 20) {
  a <- subspecialty_table(d, "dx", min_n); b <- subspecialty_table(d, "mgmt", min_n)
  do.call(rbind, lapply(1:6, function(k) {
    x <- a[a$condition == k & a$eligible_cases >= min_n, ]; y <- b[b$condition == k & b$eligible_cases >= min_n, ]
    mm <- merge(x[, c("subspecialty", "accuracy")], y[, c("subspecialty", "accuracy")], by = "subspecialty")
    st <- if (nrow(mm) >= 3) suppressWarnings(cor.test(mm$accuracy.x, mm$accuracy.y, method = "spearman")) else NULL
    data.frame(condition = k, label = COND_LABEL[as.character(k)], n_subspecialties = nrow(mm),
               spearman_rho = if (is.null(st)) NA else unname(st$estimate),
               p_value = if (is.null(st)) NA else st$p.value, note = "exploratory; subspecialties with >= 20 cases")
  }))
}

modality_table <- function(d) {
  rows <- list()
  m <- main_runs(d, "dx")
  long <- do.call(rbind, lapply(seq_len(nrow(m)), function(i) {
    mods <- strsplit(ifelse(is.na(m$modalities[i]), "", m$modalities[i]), ";")[[1]]
    if (!length(mods)) mods <- "Not recorded"
    data.frame(case_id = m$case_id[i], modality = mods)
  }))
  long <- unique(long)
  for (mo in MODELS) for (md in sort(unique(long$modality))) {
    cs <- long$case_id[long$modality == md]
    ca <- which(COND_LABEL == paste(mo, "/ Text + image")); cb <- which(COND_LABEL == paste(mo, "/ Text only"))
    t <- pair_table(d, "dx", ca, cb, cs)
    ci <- newcombe_paired(t$a, t$b, t$c, t$d)
    rows[[length(rows) + 1]] <- data.frame(model = mo, modality = md, paired_cases = t$n,
      acc_text_image = if (t$n) (t$a + t$b) / t$n else NA, acc_text_only = if (t$n) (t$a + t$c) / t$n else NA,
      diff_pp = 100 * ci[["diff"]], lower_pp = 100 * ci[["lower"]], upper_pp = 100 * ci[["upper"]],
      note = "exploratory; a case contributes to every modality it contains")
  }
  do.call(rbind, rows)
}

partial_table <- function(d) {
  m <- main_runs(d, "dx")
  m$lenient <- as.numeric(m$dx_final == 1 | (!is.na(m$partial_final) & m$partial_final == 1))
  do.call(rbind, lapply(1:6, function(k) {
    mk <- m[m$condition == k, ]; x <- sum(mk$lenient); n <- nrow(mk); ci <- wilson_ci(x, n)
    data.frame(condition = k, label = COND_LABEL[as.character(k)], strict_correct = sum(mk$dx_final),
               partial_only = sum(mk$lenient) - sum(mk$dx_final), lenient_correct = x, denominator = n,
               lenient_accuracy = if (n) x / n else NA, ci_lower = ci[1], ci_upper = ci[2])
  }))
}

interp_table <- function(d) {
  m <- d[d$run_type == "Main" & d$eligible == "Yes" & d$input == "text_image" & d$run_status == "completed", ]
  cats <- c("Correct", "Partly correct", "Incorrect", "Invented findings", "Not described")
  do.call(rbind, lapply(MODELS, function(mo) {
    s <- m[m$model == mo, ]; tot <- sum(!is.na(s$interp_final))
    data.frame(model = mo, category = c(cats, "Not yet graded"),
               n = c(sapply(cats, function(cc) sum(s$interp_final == cc, na.rm = TRUE)), sum(is.na(s$interp_final))),
               denominator_graded = tot,
               percent_of_graded = c(100 * sapply(cats, function(cc) sum(s$interp_final == cc, na.rm = TRUE)) / max(tot, 1), NA))
  }))
}

duration_citations <- function(d) {
  m <- d[d$run_type == "Main" & d$eligible == "Yes" & d$run_status == "completed", ]
  q <- function(v) { v <- v[!is.na(v)]; if (!length(v)) return(c(NA, NA, NA, 0)); c(quantile(v, c(.5, .25, .75), names = FALSE), length(v)) }
  do.call(rbind, lapply(1:6, function(k) {
    s <- m[m$condition == k, ]; a <- q(s$response_duration_s); b <- q(s$citation_count)
    data.frame(condition = k, label = COND_LABEL[as.character(k)],
               duration_median_s = a[1], duration_q1 = a[2], duration_q3 = a[3], duration_n = a[4],
               citations_median = b[1], citations_q1 = b[2], citations_q3 = b[3], citations_n = b[4])
  }))
}

retrieval_rates <- function(d) {
  m <- d[d$run_type == "Main" & d$eligible == "Yes" & d$run_status == "completed", ]
  do.call(rbind, lapply(1:6, function(k) {
    s <- m[m$condition == k, ]; yes <- sum(s$source_retrieved == "Yes", na.rm = TRUE)
    assessed <- sum(s$source_retrieved %in% c("Yes", "No")); ci <- wilson_ci(yes, assessed)
    data.frame(condition = k, label = COND_LABEL[as.character(k)], model = MODELS[(k + 1) %/% 2],
               retrieved = yes, assessed = assessed, unclear = sum(s$source_retrieved == "Unclear", na.rm = TRUE),
               not_assessed = sum(is.na(s$source_retrieved)), rate = if (assessed) yes / assessed else NA,
               ci_lower = ci[1], ci_upper = ci[2])
  }))
}

intergrader <- function(d) {
  m <- d[d$eligible == "Yes" & d$run_status == "completed", ]
  do.call(rbind, lapply(c("dx", "mgmt"), function(o) {
    do.call(rbind, lapply(c("All", MODELS), function(mo) {
      s <- if (mo == "All") m else m[m$model == mo, ]
      k <- cohen_kappa(s[[paste0(o, "_g1")]], s[[paste0(o, "_g2")]])
      data.frame(outcome = o, group = mo, pairs = k[["n"]], percent_agreement = 100 * k[["agree"]],
                 kappa = k[["kappa"]], lower = k[["lower"]], upper = k[["upper"]],
                 note = "pre-adjudication scores; main and retest responses")
    }))
  }))
}

test_retest <- function(d) {
  r <- d[d$run_type == "Retest" & d$eligible == "Yes", ]
  mm <- d[d$run_type == "Main", c("run_id", "dx_final", "mgmt_final", "analyzable_dx", "analyzable_mgmt")]
  names(mm) <- c("linked_main_run_id", "dx_main", "mgmt_main", "an_dx_main", "an_mgmt_main")
  r <- merge(r, mm, by = "linked_main_run_id")
  do.call(rbind, lapply(c("dx", "mgmt"), function(o) do.call(rbind, lapply(1:6, function(k) {
    s <- r[r$condition == k & r[[paste0("analyzable_", o)]] == 1 & r[[paste0("an_", o, "_main")]] == 1, ]
    kk <- cohen_kappa(s[[paste0(o, "_main")]], s[[OUTCOMES[[o]]]])
    data.frame(outcome = o, condition = k, label = COND_LABEL[as.character(k)], pairs = kk[["n"]],
               percent_agreement = 100 * kk[["agree"]], kappa = kk[["kappa"]], lower = kk[["lower"]], upper = kk[["upper"]],
               median_interval_days = if (nrow(s)) median(s$elapsed_days_since_main, na.rm = TRUE) else NA)
  }))))
}

historical_comparison <- function(d, hist) {
  a <- accuracy_by_condition(d, "dx"); b <- accuracy_by_condition(d, "mgmt")
  ci_dx <- wilson_ci(hist$dx_correct, hist$n_cases); ci_mg <- wilson_ci(hist$mgmt_correct, hist$n_cases)
  rbind(
    data.frame(source = hist$label, outcome = c("dx", "mgmt"), correct = c(hist$dx_correct, hist$mgmt_correct),
               denominator = hist$n_cases, accuracy = c(hist$dx_correct, hist$mgmt_correct) / hist$n_cases,
               ci_lower = c(ci_dx[1], ci_mg[1]), ci_upper = c(ci_dx[2], ci_mg[2])),
    data.frame(source = "This study: Osler / Text only (closest successor condition)", outcome = c("dx", "mgmt"),
               correct = c(a$correct[1], b$correct[1]), denominator = c(a$denominator[1], b$denominator[1]),
               accuracy = c(a$accuracy[1], b$accuracy[1]), ci_lower = c(a$ci_lower[1], b$ci_lower[1]),
               ci_upper = c(a$ci_upper[1], b$ci_upper[1])))
}

# ---------------------------------------------------------------- power
# Exact power of the two-sided exact McNemar test.
# p10 = P(A correct, B wrong), p01 = P(A wrong, B correct); n paired cases.
mcnemar_power <- function(n, p10, p01, alpha = 0.05) {
  pd <- p10 + p01; if (pd <= 0) return(0)
  pi1 <- p10 / pd
  k <- 1:n
  # lower critical value: largest x with two-sided exact p = 2 * P(X <= x) <= alpha (symmetric under H0)
  lo <- qbinom(alpha / 2, k, 0.5) ; lo <- ifelse(2 * pbinom(lo, k, 0.5) <= alpha, lo, lo - 1)
  rej <- ifelse(lo >= 0, pbinom(lo, k, pi1) + pbinom(k - lo - 1, k, pi1, lower.tail = FALSE), 0)
  sum(dbinom(k, n, pd) * rej)
}

# smallest absolute paired difference detectable with the target power
min_detectable_diff <- function(n, discordance, alpha = 0.05, power = 0.80, step = 0.0025) {
  for (dd in seq(step, discordance, by = step)) {
    if (mcnemar_power(n, (discordance + dd) / 2, (discordance - dd) / 2, alpha) >= power) return(dd)
  }
  NA
}
