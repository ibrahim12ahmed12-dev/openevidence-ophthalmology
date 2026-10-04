# Dependency check. Required: lme4, emmeans, ggplot2, jsonlite (tests: testthat).
# Install once with:
#   install.packages(c("lme4", "emmeans", "ggplot2", "jsonlite", "testthat"))
# Tested with R 4.3.3, lme4 1.1-35, emmeans 1.10.0, ggplot2 3.4.4 (see outputs/sessionInfo.txt).
check_packages <- function(pkgs) {
  miss <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
  if (length(miss)) stop("Missing R packages: ", paste(miss, collapse = ", "),
                         "\nInstall with install.packages(c(", paste0('"', miss, '"', collapse = ", "), "))")
  invisible(TRUE)
}
