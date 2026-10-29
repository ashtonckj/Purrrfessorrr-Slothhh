"""R versions of the cards' snippets, written to match the Python ones step by step.

Base R only, so there is nothing to install (readxl for .xlsx files, and nnet, which ships with R,
for a multi-class model). Pure functions of names and numbers: `local.py` decides what to say, this
file only knows how to say it in R. Snippets share one `df`, like the Python ones, and only the
first (loading) snippet reads the file.
"""

from __future__ import annotations

import json
import re

from ..files import parse_number

# json.dumps writes characters above U+FFFF as a surrogate pair, which R rejects; R wants \U{...}.
_SURROGATES = re.compile(r"\\u(d[89ab][0-9a-f]{2})\\u(d[c-f][0-9a-f]{2})", re.IGNORECASE)


def q(text: str) -> str:
    """A column or file name as an R string literal: quotes, backslashes and newlines stay escaped inside it."""
    return _SURROGATES.sub(
        lambda m: "\\U{%x}"
        % (0x10000 + ((int(m[1], 16) - 0xD800) << 10) + (int(m[2], 16) - 0xDC00)),
        json.dumps(text),
    )


# Python codec name -> the name R's file() expects.
R_ENCODINGS = {
    "utf-8-sig": "UTF-8-BOM",
    "utf-16": "UTF-16",
    "cp1252": "windows-1252",
    "latin-1": "latin1",
}


def vec(items: list[str]) -> str:
    return "c(" + ", ".join(q(i) for i in items) + ")"


def loader(
    filename: str,
    na_values: list[str],
    excluded: list[tuple[str, str]],
    kept: list[str],
    total: int,
    encoding: str = "utf-8-sig",
    dedupe: bool = False,
) -> str:
    """`df <- ...` plus the user's row filter and column choice.

    `encoding` is how the app decoded the file (Python's name for it); `dedupe` is set when the app
    renamed repeated column names, which `make.unique` reproduces (amount, amount.1).
    """
    low = filename.lower()
    if low.endswith(".xlsx"):
        repair = ', .name_repair = "minimal"' if dedupe else ""
        read = f"as.data.frame(readxl::read_excel({q(filename)}, na = {vec(na_values)}{repair}))"
    else:
        fn = "read.delim" if low.endswith(".tsv") else "read.csv"
        read = (
            f"{fn}({q(filename)}, na.strings = {vec(na_values)}, strip.white = TRUE, check.names = FALSE,\n"
            f"  stringsAsFactors = FALSE, fileEncoding = {q(R_ENCODINGS.get(encoding, 'UTF-8-BOM'))})"
        )
    code = f"df <- {read}"
    if dedupe:
        code += "\nnames(df) <- make.unique(names(df))"
    for col, value in excluded:
        num = parse_number(value)
        if value == "":  # blank cells are read as NA
            code += f"\ndf <- df[!is.na(df[[{q(col)}]]), ]"
        elif num is not None:
            code += f"\ndf <- df[!(suppressWarnings(as.numeric(df[[{q(col)}]])) %in% {num!r}), ]"
        else:
            code += f"\ndf <- df[!(df[[{q(col)}]] %in% {q(value)}), ]"
    if len(kept) < total:
        code += f"\ndf <- df[, {vec(kept)}, drop = FALSE]"
    return code


def number(col: str) -> str:
    return f"suppressWarnings(as.numeric(df[[{q(col)}]]))"


# ---------------------------------------------------------------- detective


def outliers(read: str, col: str) -> str:
    return f"""{read}
s <- {number(col)}
q <- quantile(s, c(0.25, 0.75), na.rm = TRUE)
iqr <- q[[2]] - q[[1]]
mask <- !is.na(s) & (s < q[[1]] - 1.5 * iqr | s > q[[2]] + 1.5 * iqr)
cat(sum(mask), "suspicious rows\\n")
head(df[mask, ])"""


DUPLICATES = """dupes <- df[duplicated(df), ]
cat(nrow(dupes), "duplicate rows\\n")
df <- df[!duplicated(df), ]"""


def types(col: str) -> str:
    return f"""bad <- is.na({number(col)}) & !is.na(df[[{q(col)}]])
print(head(unique(df[[{q(col)}]][bad]), 10))
df[[{q(col)}]] <- suppressWarnings(as.numeric(gsub("[$,]", "", as.character(df[[{q(col)}]]))))"""


# ------------------------------------------------------------------- artist


def histogram(col: str, bins: int) -> str:
    """Equal-width bins from min to max, like matplotlib."""
    return f"""x <- {number(col)}
r <- range(x, na.rm = TRUE)
hist(x, breaks = if (r[1] < r[2]) seq(r[1], r[2], length.out = {bins + 1}) else {bins},
     col = "grey80", main = {q(col)}, xlab = {q(col)}, ylab = "count")"""


def boxplot(col: str) -> str:
    """Drawn with bxp() from quantile() (type 7, the same quartiles as pandas), not boxplot()'s own hinges,
    so the box matches the app's. A flat middle half gets whiskers over the whole range and no dots."""
    return f"""x <- {number(col)}
x <- x[!is.na(x)]
q <- quantile(x, c(0.25, 0.5, 0.75))
iqr <- q[[3]] - q[[1]]
fence <- if (iqr > 0) c(q[[1]] - 1.5 * iqr, q[[3]] + 1.5 * iqr) else range(x)
out <- x[x < fence[1] | x > fence[2]]
whiskers <- range(x[x >= fence[1] & x <= fence[2]])
bxp(list(stats = matrix(c(whiskers[1], q, whiskers[2])), n = length(x), out = out,
         group = rep(1, length(out)), names = {q(col)}), main = {q("Box plot of " + col)})"""


def number_summary(cols: list[str]) -> str:
    return f"""nums <- sapply(df[{vec(cols)}], function(x) suppressWarnings(as.numeric(x)))
print(round(t(apply(nums, 2, quantile, na.rm = TRUE)), 2))
print(round(colMeans(nums, na.rm = TRUE), 2))"""


def category_counts(cols: list[str]) -> str:
    return f"""for (col in {vec(cols)}) {{
  cat("\\n", col, "-", length(unique(na.omit(df[[col]]))), "distinct values\\n")
  print(head(sort(table(df[[col]]), decreasing = TRUE), 5))
}}"""


def heatmap(cols: list[str]) -> str:
    return f"""nums <- sapply(df[{vec(cols)}], function(x) suppressWarnings(as.numeric(x)))
r <- cor(nums, use = "pairwise.complete.obs")
print(round(r, 2))
heatmap(r, Rowv = NA, Colv = NA, symm = TRUE, scale = "none",
        main = "Correlation does not prove causation")"""


def by_category(group: str, num: str | None) -> str:
    if num is None:
        return f"""barplot(sort(table(df[[{q(group)}]]), decreasing = TRUE), las = 2)"""
    return f"""means <- sort(tapply({number(num)}, df[[{q(group)}]], mean, na.rm = TRUE), decreasing = TRUE)
barplot(means, las = 2, ylab = {q("mean " + num)})"""


def trend(date: str, num: str) -> str:
    return f"""when <- as.Date(substr(as.character(df[[{q(date)}]]), 1, 10))
monthly <- tapply({number(num)}, format(when, "%Y-%m"), sum, na.rm = TRUE)
plot(monthly, type = "b", xaxt = "n", xlab = {q(date + " (by month)")}, ylab = {q(num)})
axis(1, at = seq_along(monthly), labels = names(monthly), las = 2)"""


def scatter(x: str, y: str) -> str:
    return f"""x <- {number(x)}
y <- {number(y)}
plot(x, y, pch = 20, xlab = {q(x)}, ylab = {q(y)})
print(cor(x, y, use = "complete.obs"))"""


# -------------------------------------------------------------------- coder


def load_peek(read: str, rows: int, cols: int) -> str:
    return f"""{read}
cat(nrow(df), "rows,", ncol(df), "columns\\n")     # ({rows}, {cols})
str(df)
print(head(sort(colSums(is.na(df)), decreasing = TRUE), 10))
head(df)"""


def summary_stats(group: str | None, num: str | None) -> str:
    code = "print(summary(df))"
    if group:
        code += f"\n\nprint(head(sort(table(df[[{q(group)}]]), decreasing = TRUE), 10))"
        if num:
            code += (
                f"\nprint(sapply(split({number(num)}, df[[{q(group)}]]), function(x)"
                " round(c(count = sum(!is.na(x)), mean = mean(x, na.rm = TRUE), median = median(x, na.rm = TRUE)), 2)))"
            )
    return code


def baseline(target: str, classify: bool) -> str:
    """A train/test baseline on a copy of `df` (so later snippets still see the original column names)."""
    first = (
        "data[[target]] <- factor(data[[target]])"
        if classify
        else "data[[target]] <- suppressWarnings(as.numeric(data[[target]]))\ndata <- data[!is.na(data[[target]]), ]"
    )
    fit = (
        'nnet::multinom(reformulate(".", response = target), data = train, trace = FALSE)'
        if classify
        else 'lm(reformulate(".", response = target), data = train)'
    )
    score = (
        'cat("accuracy:", round(mean(predict(fit, test) == test[[target]]), 3), "\\n")'
        if classify
        else "pred <- suppressWarnings(predict(fit, test))\n"
        'cat("R^2:", round(1 - sum((test[[target]] - pred)^2) / sum((test[[target]] - mean(test[[target]]))^2), 3), "\\n")'
    )
    return f"""set.seed(42)
data <- df[!is.na(df[[{q(target)}]]), ]
data <- data[, colSums(!is.na(data)) > 0, drop = FALSE]
target <- which(names(data) == {q(target)})
names(data) <- make.names(names(data), unique = TRUE)     # model formulas need plain names
target <- names(data)[target]
{first}

# fill gaps (median for numbers, most common value for text) and drop columns that never change
for (col in setdiff(names(data), target)) {{
  if (is.numeric(data[[col]])) {{
    data[[col]][is.na(data[[col]])] <- median(data[[col]], na.rm = TRUE)
  }} else {{
    common <- names(which.max(table(data[[col]])))
    data[[col]] <- factor(ifelse(is.na(data[[col]]), common, as.character(data[[col]])))
  }}
}}
data <- data[, sapply(data, function(x) length(unique(x)) > 1) | names(data) == target, drop = FALSE]

idx <- sample(nrow(data), round(0.8 * nrow(data)))
train <- data[idx, , drop = FALSE]
test <- data[-idx, , drop = FALSE]
fit <- {fit}
for (col in names(fit$xlevels)) test <- test[test[[col]] %in% fit$xlevels[[col]], ]   # levels the model never saw
{score}"""


# ------------------------------------------------------------------ janitor

FILL_MISSING = """num_cols <- names(df)[sapply(df, is.numeric)]
txt_cols <- setdiff(names(df), num_cols)
for (col in num_cols) df[[col]][is.na(df[[col]])] <- median(df[[col]], na.rm = TRUE)
for (col in txt_cols) df[[col]][is.na(df[[col]])] <- "unknown\""""


def encode(col: str) -> str:
    return f"""df[[{q(col)}]] <- tolower(trimws(as.character(df[[{q(col)}]])))
for (level in sort(unique(df[[{q(col)}]]))) df[[paste0({q(col)}, "_", level)]] <- as.integer(df[[{q(col)}]] %in% level)
df[[{q(col)}]] <- NULL"""


def recipe(fix: list[str], out_file: str) -> str:
    fixes = "".join(
        f'\n  df[[{q(c)}]] <- suppressWarnings(as.numeric(gsub("[$,]", "", as.character(df[[{q(c)}]]))))'
        for c in fix
    )
    return f"""clean <- function(df) {{
  df <- df[!duplicated(df), ]{fixes}
  is_num <- sapply(df, is.numeric)
  for (col in names(df)[is_num]) df[[col]][is.na(df[[col]])] <- median(df[[col]], na.rm = TRUE)
  for (col in names(df)[!is_num]) df[[col]] <- trimws(ifelse(is.na(df[[col]]), "unknown", as.character(df[[col]])))
  df
}}

df_clean <- clean(df)
write.csv(df_clean, {q(out_file)}, row.names = FALSE)"""
