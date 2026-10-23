# Baseline EDA specification

What the cats check on **every** upload, when each check applies, and how. The pipeline is
plain Python (`backend/engines/local.py`): no language model decides what runs, so the same
file always gives the same report, and two files with the same kinds of columns get the same
cards.

Column kinds are inferred per column: **number** (at least 90% of non-empty cells parse as
numbers), **date** (at least 80% look like `YYYY-MM-DD` or `D/M/Y`), otherwise **text**. A
*measure* is a number column whose name does not look like an ID (`id`, `*_id`, `index`, `key`).
Missing means empty, `NA`, `N/A`, `NaN`, `null`, `#N/A` or `<NA>` (but not `None`, which is often a real answer).

## The checks

| Check | Card id | Runs when | Method and defaults |
|---|---|---|---|
| Size and column overview | `scribe-summary` | always | rows, columns, kinds, an example value, missing and distinct counts per column |
| Data types and type problems | `detective-types` | always | number columns with stray text (`"$3.50"`, `"?"`) are listed with examples |
| Missing values | `janitor-missing` | always | count and % per column; plan: median for numbers, `"unknown"` for text, drop if over 40% empty |
| Duplicate rows | `detective-duplicates` | always | exact copies of an earlier row (all chosen columns equal) |
| Number summaries | `scribe-numbers` | at least one measure | min, Q1, median, mean, Q3, max, std (quartiles: inclusive method, same as pandas) |
| Distribution | `artist-distribution` | a measure exists | histogram of the target (if it is a number) or the first measure; 10 equal-width bins from min to max |
| Categories and cardinality | `scribe-categories` | at least one text column | distinct count, top 3 values; notes single-value, near-unique (ID or free text?) and over-50-category columns |
| Category comparison | `artist-by-category` | a text column with 2-50 categories | mean of the main measure per category (or row counts), top 10 |
| Trend | `artist-trend` | a date column and a measure | monthly sum of the main measure, last 36 months |
| Outliers | `detective-outliers` | always (counted for measures with more than 2 distinct values) | **potential** outliers: outside Q1 - 1.5 IQR .. Q3 + 1.5 IQR (Tukey's fences). Not confirmed errors |
| Strongest relationship | `artist-scatter` | two measures with more than 2 distinct values | Pearson r for every pair (on up to 5,000 sampled rows); scatter of the strongest |
| All correlations | `artist-correlations` | three or more such measures | every pair's r, strongest first. A pattern, not causation |
| Target analysis | `coder-baseline` and the focus of the charts | a target is picked (or a measure exists) | the target is charted first; baseline model: linear regression for numbers, logistic for text |
| Encoding plan | `janitor-encoding` | always | one-hot up to 12 categories, frequency/target encoding above |
| Cleaning recipe | `janitor-recipe` | always | dedupe, fix types, fill gaps, trim text, in that order, as code to run yourself |
| Quality warnings | `scribe-watch-out` | always | outliers, type problems, worst missing column, duplicates, mixed date formats |
| Data health score | sloth, end of run | always | 100 minus capped penalties: missing (40), duplicates (25), outlier rows (25), type problems (20) |

Charts are capped at 10 bars; tables keep everything. Statistics use every row after the user's
row filter; only the correlation ranking samples rows on very large files.

## Suggested extra analyses (not run)

`scribe-closer-look` lists analyses the baseline does **not** run, each shown next to the number
that triggered it. They are suggestions to test, not findings:

| Evidence | Suggestion |
|---|---|
| Pearson's median skewness, 3 (mean - median) / std, above 0.5 on a non-negative measure | look at it on a log scale |
| two measures with r of at least 0.9 | one may be computed from the other; keep one for a model |
| a column 5-40% empty | check whether the gaps follow a pattern before filling |
| a text target with one class at 80% or more | imbalanced classes: judge a model by more than accuracy |

The card only appears when something triggers it. The language model may explain these in chat,
but it never adds a check to the baseline.

## Code templates

Every card's Python and R code is generated from the same values the card shows, by one function
per kind of analysis (for example `histogram_card()` in `local.py` and `rcode.histogram()`). Only
column names, file names and settings change between datasets, so the same request gives the
same code structure on any file. Each snippet's imports are read back from the code itself when
the chat explains what to install.

## Changing an analysis from the chat

The histogram is stored as a spec on its card:

```json
{"kind": "histogram", "column": "total", "bins": 10, "title": "total", "x_label": "total", "y_label": "count"}
```

A request like "use 30 bins", "show the distribution of rating", "change the title to Daily
sales" or "undo" changes a copy of that spec. The backend checks it (the column must be a number
column in this file, 2 to 100 bins, labels up to 80 printable characters), re-reads only that
column, and rebuilds the chart, table and both code snippets from the spec. The rest of the
analysis is not re-run, the uploaded file is never changed, and the previous version is kept
for "undo". Other chart kinds (box plots, ...) are explained as not supported yet rather than
faked.
