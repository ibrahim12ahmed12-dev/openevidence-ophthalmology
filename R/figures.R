# Figure templates. Every panel shows denominators; synthetic runs carry a banner.
fig_theme <- function() ggplot2::theme_minimal(base_size = 11) +
  ggplot2::theme(panel.grid.minor = ggplot2::element_blank(), legend.position = "bottom",
                 plot.subtitle = ggplot2::element_text(colour = "#b00020", face = "bold"))

make_figures <- function(acc, pt, sub, rr, dir, banner = "") {
  library(ggplot2)
  sv <- function(p, f, w = 8, h = 5) ggsave(file.path(dir, f), p, width = w, height = h, dpi = 200, bg = "white")
  sub_title <- if (nzchar(banner)) banner else NULL

  # F1 accuracy by condition
  a <- acc; a$outcome <- OUTCOME_LABEL[a$outcome]; a$input <- INPUT_LABEL[a$input]
  a$model <- factor(a$model, MODELS)
  p1 <- ggplot(a, aes(model, accuracy, colour = input)) +
    geom_pointrange(aes(ymin = ci_lower, ymax = ci_upper), position = position_dodge(0.5)) +
    geom_text(aes(label = paste0(correct, "\n/", denominator), y = ci_lower - 0.06), position = position_dodge(0.5),
              size = 2.5, lineheight = 0.85, show.legend = FALSE) +
    facet_wrap(~outcome) + scale_y_continuous(labels = function(x) paste0(100 * x, "%"), limits = c(0, 1)) +
    scale_colour_manual(values = c("Text only" = "#3b6ea8", "Text + image" = "#d08a2e")) +
    labs(x = NULL, y = "Accuracy (95% Wilson CI)", colour = NULL, title = "Accuracy by condition (main runs)", subtitle = sub_title) + fig_theme()
  sv(p1, "F1_accuracy_by_condition.png")

  # F2 paired input difference by model
  f1 <- pt[pt$family == "F1_input_within_model", ]
  f1$model <- factor(sub(" /.*", "", f1$comparison), MODELS); f1$outcome <- OUTCOME_LABEL[f1$outcome]
  p2 <- ggplot(f1, aes(diff_pp, model)) + geom_vline(xintercept = 0, linetype = 2, colour = "grey50") +
    geom_pointrange(aes(xmin = diff_lower_pp, xmax = diff_upper_pp)) +
    geom_text(aes(label = paste0("n=", paired_cases, " pairs")), vjust = -1, size = 2.8) + facet_wrap(~outcome) +
    labs(x = "Text + image minus text only (percentage points, Newcombe 95% CI)", y = NULL,
         title = "Paired effect of image substitution within each model", subtitle = sub_title) + fig_theme()
  sv(p2, "F2_paired_input_difference.png", h = 4)

  # F3 subspecialty (descriptive)
  s <- sub; s$outcome <- OUTCOME_LABEL[s$outcome]
  s$subspecialty_n <- paste0(s$subspecialty, " (n=", s$eligible_cases, ")")
  s$subspecialty_n <- factor(s$subspecialty_n, unique(s$subspecialty_n[order(s$eligible_cases)]))
  pal <- c("Osler / Text only" = "#9ecae1", "Osler / Text + image" = "#2171b5",
           "Sackett / Text only" = "#a1d99b", "Sackett / Text + image" = "#238b45",
           "Snow / Text only" = "#fdae6b", "Snow / Text + image" = "#d94801")
  s$label <- factor(s$label, names(pal))
  p3 <- ggplot(s, aes(accuracy, subspecialty_n, colour = label)) + geom_point(position = position_dodge(0.6)) +
    facet_wrap(~outcome) + scale_x_continuous(labels = function(x) paste0(100 * x, "%")) +
    scale_colour_manual(values = pal) +
    labs(x = "Accuracy", y = NULL, colour = NULL, title = "Accuracy by subspecialty",
         caption = "Descriptive only. Groups with fewer than 20 cases are not tested; their estimates are very imprecise.",
         subtitle = sub_title) + fig_theme() + guides(colour = guide_legend(nrow = 2))
  sv(p3, "F3_subspecialty.png", h = 6)

  # F4 retrieval rates
  r <- rr; r$label <- factor(r$label, r$label)
  p4 <- ggplot(r, aes(label, rate)) + geom_col(fill = "#6c757d") +
    geom_errorbar(aes(ymin = ci_lower, ymax = ci_upper), width = 0.2) +
    geom_text(aes(label = paste0(retrieved, "/", assessed), y = pmax(ci_upper, rate, na.rm = TRUE) + 0.01), size = 2.8) +
    scale_y_continuous(labels = function(x) paste0(100 * x, "%")) +
    labs(x = NULL, y = "Runs citing the source case", title = "Source-case retrieval by condition (assessed runs)", subtitle = sub_title) +
    fig_theme() + theme(axis.text.x = element_text(angle = 25, hjust = 1))
  sv(p4, "F4_retrieval_rates.png", h = 4.5)
  invisible(TRUE)
}
