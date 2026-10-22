"""Mock engine: five cats working in parallel on made-up (but plausible) results.

It peeks at the first few hundred rows of the real upload so the cards mention
your actual column names, then invents the numbers. Seeded by file name + row
count, so the same file gives the same story every time.
"""

from __future__ import annotations

import asyncio
import csv
import random
import re
from dataclasses import dataclass

from ..cats import CAT_IDS, paper_total, split_papers
from ..files import FileInfo
from ..jobs import Job
from . import mock_copy as copy
from .base import Engine

PEEK_ROWS = 400


@dataclass
class Peek:
    columns: list[str]
    numeric: list[str]
    categorical: list[str]
    samples: dict[str, list[str]]
    date_col: str | None = None
    number_cols: list[str] | None = None  # every numeric-looking column, ids included


class MockEngine(Engine):
    name = "mock"

    def __init__(self, speed: float = 1.0, error_rate: float = 0.0) -> None:
        self.speed = speed
        self.error_rate = error_rate

    # ------------------------------------------------------------------ run

    async def run(self, job: Job) -> None:
        info = job.file
        rng = random.Random(f"{info.filename}:{info.rows}")
        peek = await asyncio.to_thread(_peek, info)

        total, _capped = paper_total(info.rows)
        for cat, count in split_papers(total).items():
            await job.emit("delegated", cat=cat, paper_count=count)

        # Give the frontend time to fly the papers to the desks.
        await asyncio.sleep(2.5 * self.speed)

        stats = _fake_stats(rng, info, peek)
        cards = {
            "detective": _detective_cards(rng, info, peek, stats),
            "artist": _artist_cards(rng, info, peek),
            "scribe": _scribe_cards(rng, info, peek, stats),
            "coder": _coder_cards(info, peek),
            "janitor": _janitor_cards(rng, info, peek, stats),
        }
        done_vars = {
            "outliers": stats["outlier_rows"],
            "charts": len(cards["artist"]),
            "snippets": len(cards["coder"]),
            "missing": stats["missing_total"],
        }

        await asyncio.gather(*(
            self._run_cat(job, cat, cards[cat], done_vars, random.Random(rng.random()))
            for cat in CAT_IDS
        ))
        await job.emit("done", health_score=stats["health_score"])

    async def _run_cat(self, job: Job, cat: str, cards: list[dict], done_vars: dict, rng: random.Random) -> None:
        duration = rng.uniform(6, 18) * self.speed
        fail_at = rng.randint(20, 85) if rng.random() < self.error_rate else None
        lines = copy.PROGRESS_LINES[cat]

        percent = 0
        await job.emit("progress", cat=cat, percent=0, message=lines[0])
        while percent < 100:
            step = rng.randint(4, 12)
            await asyncio.sleep(duration * step / 100)
            percent = min(100, percent + step)
            if fail_at is not None and percent >= fail_at:
                await job.emit("error", cat=cat, message=rng.choice(copy.ERROR_LINES))
                return
            line = lines[min(len(lines) - 1, percent * len(lines) // 100)]
            await job.emit("progress", cat=cat, percent=percent, message=line)

        await job.emit("progress", cat=cat, percent=100, message=copy.DONE_LINES[cat].format(**done_vars))
        await job.emit("result", cat=cat, cards=cards)

    # ----------------------------------------------------------------- chat

    async def chat(self, job: Job | None, message: str) -> str:
        await asyncio.sleep(1.2 * self.speed)  # sloths reply slowly
        rng = random.Random()
        if job is None:
            return rng.choice(copy.CHAT_NO_JOB)
        text = message.lower()
        if job.health_score is not None and any(w in text for w in ("health", "score", "quality", "clean")):
            score = job.health_score
            mood = "happy" if score > 80 else "grumpy" if score < 40 else "meh"
            return copy.CHAT_HEALTH.format(score=score, mood=copy.HEALTH_MOOD[mood])
        return rng.choice(copy.CHAT_REPLIES)


# ---------------------------------------------------------------- helpers


def _peek(info: FileInfo) -> Peek:
    """Read a few rows to guess which columns are numeric."""
    samples: dict[str, list[str]] = {c: [] for c in info.columns}
    ext = info.path.suffix.lower()
    try:
        if ext == ".xlsx":
            from openpyxl import load_workbook

            wb = load_workbook(info.path, read_only=True, data_only=True)
            rows = wb.worksheets[0].iter_rows(values_only=True)
            next(rows, None)
            for i, row in enumerate(rows):
                if i >= PEEK_ROWS:
                    break
                for col, value in zip(info.columns, row):
                    samples[col].append("" if value is None else str(value))
            wb.close()
        else:
            with info.path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                head = fh.read(64 * 1024)
                fh.seek(0)
                try:
                    delim = "\t" if ext == ".tsv" else csv.Sniffer().sniff(head, ",;\t|").delimiter
                except csv.Error:
                    delim = ","
                reader = csv.reader(fh, delimiter=delim)
                next(reader, None)
                for i, row in enumerate(reader):
                    if i >= PEEK_ROWS:
                        break
                    for col, value in zip(info.columns, row):
                        samples[col].append(value)
    except Exception:  # a mock must never crash on a weird file
        pass

    numeric, categorical = [], []
    for col, values in samples.items():
        filled = [v for v in values if v.strip()]
        parsed = sum(1 for v in filled if _is_number(v))
        if filled and parsed / len(filled) >= 0.8:
            numeric.append(col)
        else:
            categorical.append(col)

    # Charts read better with real measures and small groupings: skip ids and dates,
    # prefer text columns with a handful of distinct values.
    def is_id(col: str) -> bool:
        return bool(re.search(r"(^|_)(id|index|key)$", col.lower()))

    def is_date(col: str) -> bool:
        return bool(re.search(r"date|time|day|month|year", col.lower()))

    measures = [c for c in numeric if not is_id(c)] or numeric
    groups = sorted(
        (c for c in categorical if not is_date(c) and not is_id(c)),
        key=lambda c: abs(len(set(samples[c])) - 6),
    ) or categorical
    return Peek(info.columns, measures, groups, samples,
                next((c for c in info.columns if is_date(c)), None), numeric)


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except ValueError:
        return False


def _pick(items: list[str], index: int, fallback: str) -> str:
    return items[index % len(items)] if items else fallback


def _fake_stats(rng: random.Random, info: FileInfo, peek: Peek) -> dict:
    rows = max(info.rows, 1)
    missing = {c: (rng.randint(0, max(1, rows // 12)) if rng.random() < 0.55 else 0) for c in peek.columns}
    duplicates = rng.randint(0, max(1, rows // 150))
    outlier_rows = rng.randint(1, max(2, rows // 80))
    type_issues = rng.sample(peek.numeric[:4], k=min(len(peek.numeric[:4]), rng.randint(1, 2)))
    missing_total = sum(missing.values())
    missing_pct = missing_total / (rows * max(1, len(peek.columns)))
    score = 100 - missing_pct * 1500 - duplicates / rows * 1500 - outlier_rows / rows * 800 - len(type_issues) * 8
    score = int(max(5, min(98, score + rng.uniform(-6, 6))))
    return {
        "missing": missing,
        "missing_total": missing_total,
        "duplicates": duplicates,
        "outlier_rows": outlier_rows,
        "type_issues": type_issues,
        "health_score": score,
    }


# ------------------------------------------------------------------ cards
# Every card follows the shape documented in engines/base.py.


def _detective_cards(rng: random.Random, info: FileInfo, peek: Peek, stats: dict) -> list[dict]:
    cols = (peek.numeric or peek.columns)[:6]
    counts = [rng.randint(0, max(1, stats["outlier_rows"] // 2)) for _ in cols]
    num = _pick(peek.numeric, 0, _pick(peek.columns, 0, "value"))
    outlier_table = [
        [rng.randint(2, info.rows + 1), c, round(rng.uniform(500, 9999), 2), round(rng.uniform(3.1, 9.5), 1)]
        for c in rng.choices(cols or [num], k=8)
    ]
    cards = [
        {
            "id": "detective-outliers",
            "title": f"{stats['outlier_rows']} suspicious rows",
            "description": "Values sitting far outside the usual range (beyond 1.5x the IQR). "
                           "Could be typos, could be real VIP customers. Worth a look before modelling.",
            "severity": "warn" if stats["outlier_rows"] else "ok",
            "chart": {"type": "hbar", "title": "Outliers per column", "x_label": "rows", "y_label": "column",
                      "labels": cols, "values": counts},
            "table": {"columns": ["row", "column", "value", "z_score"], "rows": outlier_table},
            "code": {"python": f"""import pandas as pd

df = pd.read_csv("{info.filename}")
q1, q3 = df["{num}"].quantile([0.25, 0.75])
iqr = q3 - q1
mask = (df["{num}"] < q1 - 1.5 * iqr) | (df["{num}"] > q3 + 1.5 * iqr)
print(mask.sum(), "suspicious rows")
df[mask].head()""", "r": None},
        },
        {
            "id": "detective-duplicates",
            "title": f"{stats['duplicates']} duplicate rows",
            "description": "Rows that are exact copies of an earlier row. Usually an export glitch; "
                           "they quietly inflate counts and averages.",
            "severity": "bad" if stats["duplicates"] > info.rows * 0.01 else "warn" if stats["duplicates"] else "ok",
            "chart": {"type": "bar", "title": "Unique vs duplicate rows", "x_label": "", "y_label": "rows",
                      "labels": ["unique", "duplicate"], "values": [info.rows - stats["duplicates"], stats["duplicates"]]},
            "table": {"columns": ["first_seen_row", "duplicate_row"],
                      "rows": sorted([[(r := rng.randint(2, info.rows)), r + rng.randint(1, 400)]
                                      for _ in range(min(10, stats["duplicates"]))])},
            "code": {"python": f"""dupes = df[df.duplicated(keep="first")]
print(len(dupes), "duplicate rows")
df = df.drop_duplicates()""", "r": None},
        },
        {
            "id": "detective-types",
            "title": f"{len(stats['type_issues'])} columns with type problems",
            "description": "Columns that are mostly numbers but contain a few strays like 'N/A', '$3.50' "
                           "or '1,200'. pandas reads the whole column as text because of them.",
            "severity": "warn" if stats["type_issues"] else "ok",
            "chart": None,
            "table": {"columns": ["column", "expected", "found", "examples"],
                      "rows": [[c, "number", "text", rng.choice(["N/A, n/a", "$3.50, $12", "1,200, 3,450", "?, -"])]
                               for c in stats["type_issues"]] or [["(none)", "", "", ""]]},
            "code": {"python": f"""bad = pd.to_numeric(df["{num}"], errors="coerce").isna() & df["{num}"].notna()
print(df.loc[bad, "{num}"].unique()[:10])
df["{num}"] = pd.to_numeric(df["{num}"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")""",
                     "r": None},
        },
    ]
    return cards


def _artist_cards(rng: random.Random, info: FileInfo, peek: Peek) -> list[dict]:
    num_a = _pick(peek.numeric, 0, "value")
    num_b = _pick(peek.numeric, 1, "other_value")
    cat = _pick(peek.categorical, 0, "group")
    date = peek.date_col or "date"
    bins = [f"{i * 10}-{i * 10 + 9}" for i in range(10)]
    hist = [int(1000 * 2.718 ** (-((i - 4.2) ** 2) / 6) + rng.randint(0, 60)) for i in range(10)]
    cat_labels = list(dict.fromkeys(v for v in peek.samples.get(cat, []) if v.strip()))[:7] or ["A", "B", "C", "D"]
    line_vals = [round(50 + i * 3 + rng.uniform(-12, 12), 1) for i in range(12)]
    points = [[round((x := rng.uniform(0, 100)), 1), round(x * 0.6 + rng.gauss(0, 12), 1)] for _ in range(80)]
    return [
        {
            "id": "artist-distribution",
            "title": f"Distribution of {num_a}",
            "description": f"A histogram, because {num_a} is one number per row. Slightly right-skewed: "
                           "most values are modest, a few are large.",
            "chart": {"type": "hist", "title": f"{num_a}", "x_label": num_a, "y_label": "count",
                      "labels": bins, "values": hist},
            "table": {"columns": ["bin", "count"], "rows": [[b, v] for b, v in zip(bins, hist)]},
            "code": {"python": f"""import matplotlib.pyplot as plt

df["{num_a}"].plot.hist(bins=10, edgecolor="black")
plt.xlabel("{num_a}"); plt.ylabel("count")
plt.show()""", "r": None},
        },
        {
            "id": "artist-by-category",
            "title": f"{num_a} by {cat}",
            "description": f"A bar chart, because {cat} has a handful of categories. "
                           "Sorted so the biggest bar is easy to spot.",
            "chart": {"type": "bar", "title": f"mean {num_a} by {cat}", "x_label": cat, "y_label": f"mean {num_a}",
                      "labels": cat_labels, "values": sorted((round(rng.uniform(10, 90), 1) for _ in cat_labels), reverse=True)},
            "code": {"python": f"""(df.groupby("{cat}")["{num_a}"].mean()
   .sort_values(ascending=False)
   .plot.bar(edgecolor="black"))
plt.show()""", "r": None},
        },
        {
            "id": "artist-trend",
            "title": f"{num_a} over time",
            "description": "A line chart across 12 periods. Gentle upward trend with some monthly wobble.",
            "chart": {"type": "line", "title": f"{num_a} per month", "x_label": "month", "y_label": num_a,
                      "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                      "values": line_vals},
            "code": {"python": f"""df["{date}"] = pd.to_datetime(df["{date}"], errors="coerce")
df.set_index("{date}")["{num_a}"].resample("MS").sum().plot(marker="s")
plt.show()""", "r": None},
        },
        {
            "id": "artist-scatter",
            "title": f"{num_a} vs {num_b}",
            "description": f"A scatter plot to check whether {num_a} and {num_b} move together. "
                           "They do, moderately (r = 0.6-ish).",
            "chart": {"type": "scatter", "title": f"{num_a} vs {num_b}", "x_label": num_a, "y_label": num_b,
                      "points": points},
            "table": {"columns": [num_a, num_b], "rows": points},
            "code": {"python": f"""df.plot.scatter(x="{num_a}", y="{num_b}", s=8)
print(df[["{num_a}", "{num_b}"]].corr())
plt.show()""", "r": None},
        },
    ]


def _scribe_cards(rng: random.Random, info: FileInfo, peek: Peek, stats: dict) -> list[dict]:
    dictionary = []
    for col in peek.columns:
        kind = "number" if col in (peek.number_cols or []) else "text / category"
        example = next((v for v in peek.samples.get(col, []) if v.strip()), "")
        dictionary.append([col, kind, example, stats["missing"].get(col, 0)])
    return [
        {
            "id": "scribe-summary",
            "title": "The data in one paragraph",
            "description": (
                f"{info.filename} has {info.rows:,} rows and {info.cols} columns. "
                f"{len(peek.number_cols or [])} columns hold numbers and {info.cols - len(peek.number_cols or [])} hold text, dates or categories. "
                f"About {stats['missing_total']:,} cells are empty and {stats['duplicates']} rows are repeated. "
                "Overall it is usable: tidy it up a little and it is ready for charts and simple models."
            ),
            "severity": "ok",
            "chart": None,
            "table": {"columns": ["column", "type", "example", "missing"], "rows": dictionary},
        },
        {
            "id": "scribe-watch-out",
            "title": "Things to watch out for",
            "description": " ".join([
                f"1) {stats['outlier_rows']} rows have extreme values; check them before averaging.",
                f"2) {len(stats['type_issues'])} number columns are stored as text.",
                "3) Missing values are not random: they cluster in a few columns.",
                "4) Dates may use mixed formats; parse them explicitly.",
            ]),
            "severity": "warn",
            "chart": None,
        },
        {
            "id": "scribe-next",
            "title": "Questions this data could answer",
            "description": "Which groups drive the totals? Is there a seasonal pattern? "
                           "Do the two strongest numeric columns predict each other? "
                           "Which rows look like data-entry mistakes?",
            "chart": None,
        },
    ]


def _coder_cards(info: FileInfo, peek: Peek) -> list[dict]:
    num = _pick(peek.numeric, 0, "value")
    target = _pick(peek.numeric, -1, "target")
    cat = _pick(peek.categorical, 0, "group")
    loader = "pd.read_excel" if info.filename.lower().endswith(".xlsx") else "pd.read_csv"
    sep = ', sep="\\t"' if info.filename.lower().endswith(".tsv") else ""
    return [
        {
            "id": "coder-load",
            "title": "Load and peek",
            "description": "Read the file and get a first look at shape, types and missing values.",
            "chart": None,
            "code": {"python": f"""import pandas as pd

df = {loader}("{info.filename}"{sep})
print(df.shape)          # ({info.rows}, {info.cols})
print(df.dtypes)
print(df.isna().sum().sort_values(ascending=False).head(10))
df.head()""", "r": None},
        },
        {
            "id": "coder-summary",
            "title": "Summary statistics",
            "description": "describe() for numbers, value_counts() for the main category.",
            "chart": None,
            "code": {"python": f"""summary = df.describe(include="number").T
summary["missing"] = df.isna().sum()
print(summary.round(2))

print(df["{cat}"].value_counts().head(10))
print(df.groupby("{cat}")["{num}"].agg(["count", "mean", "median"]).round(2))""", "r": None},
        },
        {
            "id": "coder-baseline",
            "title": "Baseline model",
            "description": f"A quick linear-regression baseline predicting {target}. "
                           "Not fancy, but it tells you whether a fancier model is worth the effort.",
            "chart": None,
            "code": {"python": f"""from sklearn.compose import make_column_transformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

X = df.drop(columns=["{target}"])
y = df["{target}"]
num_cols = X.select_dtypes("number").columns
cat_cols = X.select_dtypes(exclude="number").columns

prep = make_column_transformer(
    (SimpleImputer(strategy="median"), num_cols),
    (make_pipeline(SimpleImputer(strategy="most_frequent"),
                   OneHotEncoder(handle_unknown="ignore")), cat_cols),
)
model = make_pipeline(prep, LinearRegression())

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model.fit(X_train, y_train.fillna(y_train.median()))
print("R^2:", round(model.score(X_test, y_test.fillna(y_test.median())), 3))""", "r": None},
        },
    ]


def _janitor_cards(rng: random.Random, info: FileInfo, peek: Peek, stats: dict) -> list[dict]:
    rows = max(info.rows, 1)
    missing = sorted(stats["missing"].items(), key=lambda kv: kv[1], reverse=True)
    shown = [kv for kv in missing if kv[1]][:8] or missing[:4]
    plan = []
    for col, n in missing:
        if not n:
            continue
        pct = n / rows * 100
        if pct > 40:
            action = "drop column"
        elif col in (peek.number_cols or []):
            action = "fill with median"
        else:
            action = "fill with 'unknown'"
        plan.append([col, n, round(pct, 1), action])
    encode = []
    for col in peek.categorical[:8]:
        distinct = len(set(v for v in peek.samples.get(col, []) if v.strip()))
        encode.append([col, distinct, "one-hot" if distinct <= 12 else "frequency / target encoding"])
    num = _pick(peek.numeric, 0, "value")
    cat = _pick(peek.categorical, 0, "group")
    return [
        {
            "id": "janitor-missing",
            "title": f"{stats['missing_total']:,} missing values",
            "description": "Empty cells per column, with what I would do about each. "
                           "Numbers get the median (robust to outliers), text gets 'unknown'.",
            "severity": "bad" if stats["missing_total"] > rows * 0.1 else "warn" if stats["missing_total"] else "ok",
            "chart": {"type": "hbar", "title": "% missing per column", "x_label": "% missing", "y_label": "column",
                      "labels": [c for c, _ in shown], "values": [round(n / rows * 100, 1) for _, n in shown]},
            "table": {"columns": ["column", "missing", "percent", "action"], "rows": plan or [["(none)", 0, 0, "nothing to do"]]},
            "code": {"python": f"""num_cols = df.select_dtypes("number").columns
txt_cols = df.columns.difference(num_cols)
df[num_cols] = df[num_cols].fillna(df[num_cols].median())
df[txt_cols] = df[txt_cols].fillna("unknown")""", "r": None},
        },
        {
            "id": "janitor-encoding",
            "title": "Encoding the categories",
            "description": "Text columns need to become numbers before most models will eat them. "
                           "Few categories: one-hot. Lots of categories: frequency encoding.",
            "chart": {"type": "bar", "title": "distinct values per text column", "x_label": "column", "y_label": "distinct",
                      "labels": [r[0] for r in encode] or ["(none)"], "values": [r[1] for r in encode] or [0]},
            "table": {"columns": ["column", "distinct_values", "strategy"], "rows": encode or [["(none)", 0, ""]]},
            "code": {"python": f"""df["{cat}"] = df["{cat}"].str.strip().str.lower()
df = pd.get_dummies(df, columns=["{cat}"], prefix="{cat}", dtype=int)""", "r": None},
        },
        {
            "id": "janitor-recipe",
            "title": "Full cleaning recipe",
            "description": "Everything above in one function, in a safe order: "
                           "dedupe, fix types, fill gaps, trim text.",
            "chart": None,
            "table": {"columns": ["step", "rows_before", "rows_after"],
                      "rows": [["drop duplicates", info.rows, info.rows - stats["duplicates"]],
                               ["fix types", info.rows - stats["duplicates"], info.rows - stats["duplicates"]],
                               ["fill missing", info.rows - stats["duplicates"], info.rows - stats["duplicates"]]]},
            "code": {"python": f"""def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates().copy()
    df["{num}"] = pd.to_numeric(
        df["{num}"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    num_cols = df.select_dtypes("number").columns
    txt_cols = df.columns.difference(num_cols)
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    df[txt_cols] = df[txt_cols].fillna("unknown").apply(lambda s: s.astype(str).str.strip())
    return df

df_clean = clean(df)
df_clean.to_csv("{info.filename.rsplit('.', 1)[0]}_clean.csv", index=False)""", "r": None},
        },
    ]
