"""Local engine: real statistics over every row of the upload (standard library only).

The whole file is read once and every column is profiled (type, missing values,
outliers, duplicates, distributions); each cat turns those facts into cards.
The cats' progress is paced so the office has time to animate, but every
number they report is computed from the data.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..cats import CAT_IDS, paper_total, split_papers
from ..files import FileInfo, Selection, cell_matcher as _matcher, cell_text, iter_rows, parse_number as _number
from ..jobs import Job
from . import lines, talk
from .base import Engine, Reply

# Cells that count as missing (compared lower-cased). "None" is deliberately not here:
# it is often a real answer ("no holiday"), so it stays an ordinary value.
NA = {"", "na", "n/a", "nan", "null", "#n/a", "<na>"}
# The same list for pandas; keep_default_na=False stops it adding "None" back.
NA_VALUES = ["", "NA", "N/A", "NaN", "nan", "null", "NULL", "n/a", "#N/A", "<NA>"]
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
OTHER_DATE = re.compile(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}$")
CORR_SAMPLE = 5000   # rows used to rank column pairs by correlation
SCATTER_POINTS = 300
MAX_BARS = 10
TOP_VALUES = 50      # most common values kept per column, for chat answers
VALUE_LINES = 30     # values listed in one chat answer

q = json.dumps  # a column or file name as a Python string literal

# Chat: words that make a message a follow-up ("what about it?"), a request for detail, or a stat question.
FOLLOW_UP = re.compile(r"\b(it|its|that|those|them|same)\b|^\s*(and|also|what about|how about|why)\b")
MORE = re.compile(r"\b(more|details?|examples?|show me|which rows)\b")
SCORE_HOW = re.compile(r"\b(how|why|calculat\w*|comput\w*|formula|mean|made|work|measure\w*|based)\b")
STAT = re.compile(r"\b(mean|average|median|min|minimum|max|maximum|highest|lowest|biggest|smallest)\b")
YES = re.compile(r"(yes|yeah|yep|yup|ok|okay|sure|y|please|do it|go ahead)( please)?")
NO = re.compile(r"(no|nope|nah|n|cancel|never ?mind|forget it)")
# Words that are not column hints when matching part of a column name.
CHAT_WORDS = {"show", "tell", "with", "from", "have", "that", "this", "what", "does", "data", "about", "there",
              "which", "where", "give", "find", "look", "check", "please", "dataset", "file", "column", "columns"}
MAX_CHOICES = 6
# Questions about what is in the data (the scribe answers them from the facts).
SAMPLE = re.compile(r"\b(sample|first (few )?rows?|top rows?|few rows|some rows|head|preview|example rows?|look like)\b"
                    r"|\bshow (me )?(the )?(data|rows|dataset)\b")
COLUMNS = re.compile(r"\b(columns?|fields?|headers?|variables?)\b")
COUNT = re.compile(r"\b(how many|count|number of|how often)\b")
VALUES = re.compile(r"\b(list|unique|distinct|different|categories|category|kinds?|options|values|names?)\b"
                    r"|\b(what|which)\b[^?]*\b(are there|is there|exist|exists|appear|appears|are in|are included|do we have|do you have)\b")

# Code questions are matched separately (talk.CODE) because they need whole words.
TOPICS: dict[str, tuple[str, ...]] = {   # checked in this order
    "detective": ("outlier", "suspicious", "extreme", "duplicate", "dupe", "type problem", "dtype", "data type", "weird", "wrong", "strange"),
    "artist": ("chart", "plot", "graph", "visual", "histogram", "distribution", "trend", "correlat",
               "scatter", "relationship", "together"),
    "janitor": ("missing", "clean", "empty", "null", "blank", "fill", "encod", "preprocess", "impute"),
    "scribe": ("summary", "summar", "explain", "describe", "overview", "column", "row", "how many",
               "mean", "average", "median", "min", "max", "inside", "contain", "dataset"),
}


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def _is_id(name: str) -> bool:
    return bool(re.search(r"(^|_)(id|index|key)$", name.lower()))


@dataclass
class Col:
    name: str
    kind: str                         # "number" | "date" | "text"
    missing: int
    distinct: int
    example: str
    top: list[tuple[str, int]]        # most common values, most common first
    strays: list[str]                 # non-numbers in a number column
    stats: dict = field(default_factory=dict)   # number: min/max/mean/median/std/q1/q3, date: first/last
    numbers: list[float | None] = field(default_factory=list, repr=False)   # per row, number columns only

    @property
    def is_measure(self) -> bool:
        return self.kind == "number" and not _is_id(self.name)


@dataclass
class Facts:
    filename: str
    rows: int                         # after the user's row filter
    cols: list[Col]                   # the chosen columns
    all_columns: int                  # columns in the file
    excluded: list[tuple[str, str]]   # (column, value) rules the user set
    excluded_rows: int
    measures: list[Col]
    groups: list[Col]                 # text columns with a handful of categories
    date_col: Col | None
    target: Col | None
    focus: Col | None                 # the measure the charts are about
    missing_total: int
    duplicates: list[tuple[int, int]]                 # (first_seen_row, duplicate_row), 1-based data rows
    outlier_counts: dict[str, int]
    outlier_examples: list[list]                      # [row, column, value, z]
    outlier_rows: int
    type_issues: list[Col]
    mixed_dates: int                  # date cells not written as YYYY-MM-DD
    by_group: tuple[Col, list[tuple[str, float, int]]] | None   # group col, [(label, mean or count, n)]
    trend: list[tuple[str, float]]    # (YYYY-MM, sum of focus)
    pair: tuple[Col, Col, float, list[list[float]], bool] | None  # a, b, r, points, sampled
    hist: tuple[list[str], list[int]] | None
    health_score: int
    head: list[list[str]]             # the first kept rows, in the order of `cols`


@dataclass
class Pending:
    """A question a cat asked and is waiting on."""
    cat: str
    options: list[Col]
    default: Col | None               # what "yes" means; None when there are several equal guesses
    ask: Reply                        # repeated if the user answers with just "yes" to a list
    intent: str = "profile"           # "values" when the user asked to list a column's values


@dataclass
class Convo:
    """What the cats remember about one job's chat: the last cat and column, and any open question."""
    cat: str | None = None
    col: Col | None = None
    pending: Pending | None = None
    last: Reply | None = None         # the last reply, for "say that again"


# ------------------------------------------------------------------ engine


class LocalEngine(Engine):
    name = "local"

    def __init__(self, speed: float = 1.0) -> None:
        self.speed = speed
        self._facts: dict[str, Facts] = {}    # job id -> facts, for chat
        self._convo: dict[str, Convo] = {}

    async def run(self, job: Job) -> None:
        info = job.file
        for cat, count in split_papers(paper_total(info.rows)).items():
            await job.emit("delegated", cat=cat, paper_count=count)

        # Read the file while the papers fly to the desks.
        facts, _ = await asyncio.gather(asyncio.to_thread(analyse, info, job.selection),
                                        asyncio.sleep(2.5 * self.speed))
        self._facts[job.id] = facts

        cards: dict[str, list[dict] | Exception] = {}
        for cat in CAT_IDS:
            try:
                cards[cat] = BUILDERS[cat](facts)
            except Exception as exc:  # one cat failing must not sink the others
                cards[cat] = exc
        done_vars = {
            "outliers": f"{facts.outlier_rows:,}",
            "charts": len(cards["artist"]) if isinstance(cards["artist"], list) else 0,
            "snippets": len(cards["coder"]) if isinstance(cards["coder"], list) else 0,
            "missing": f"{facts.missing_total:,}",
        }
        rng = random.Random(job.id)
        await asyncio.gather(*(
            self._run_cat(job, cat, cards[cat], done_vars, random.Random(rng.random()))
            for cat in CAT_IDS
        ))
        await job.emit("done", health_score=facts.health_score)

    async def _run_cat(self, job: Job, cat: str, cards: list[dict] | Exception, done_vars: dict,
                       rng: random.Random) -> None:
        duration = rng.uniform(4, 10) * self.speed
        steps = lines.PROGRESS_LINES[cat]
        percent = 0
        await job.emit("progress", cat=cat, percent=0, message=steps[0])
        while percent < 100:
            step = rng.randint(6, 14)
            await asyncio.sleep(duration * step / 100)
            percent = min(100, percent + step)
            if isinstance(cards, Exception) and percent >= 50:
                await job.emit("error", cat=cat, message=f"tripped over this file ({type(cards).__name__}: {cards})")
                return
            await job.emit("progress", cat=cat, percent=percent,
                           message=steps[min(len(steps) - 1, percent * len(steps) // 100)])
        await job.emit("progress", cat=cat, percent=100, message=lines.DONE_LINES[cat].format(**done_vars))
        await job.emit("result", cat=cat, cards=cards)

    # ----------------------------------------------------------------- chat

    async def chat(self, job: Job | None, message: str) -> Reply:
        await asyncio.sleep(0.6 * self.speed)   # sloths reply slowly
        reply = self._chat(job, message)
        if job is not None and job.id in self._convo:
            self._convo[job.id].last = reply
        return reply

    def _chat(self, job: Job | None, message: str) -> Reply:
        """Read a message in this order: an open question, small talk, health, code, what is inside the data
        (columns, rows, values), a column or topic for one cat, and last any card that matches."""
        if job is None:
            return Reply("sloth", random.choice(lines.CHAT_NO_JOB))
        facts = self._facts.get(job.id)
        if facts is None:
            return Reply("sloth", lines.CHAT_NOT_READY)
        convo = self._convo.setdefault(job.id, Convo())
        text = message.lower()

        # A cat asked something last turn: this message may be the answer.
        pending, convo.pending = convo.pending, None
        if pending:
            kind, col = _resolve(pending, text, facts)
            if kind == "no":
                return Reply("sloth", lines.CHAT_NEVERMIND)
            if kind == "again":
                convo.pending = pending
                return pending.ask
            if kind != "new":
                return self._reply(job, facts, convo, pending.cat, col, intent=pending.intent)

        col = _mentioned_column(facts, text)
        code = talk.CODE.search(text)
        if code and col and code.group(0) in col.name.lower():
            code = None                        # "zip code" can be a column
        small = talk.small_talk(text)
        if small:
            return Reply("sloth", small)
        if talk.HELP.search(text) or text.strip(" ?!.") == "help":
            return Reply("sloth", lines.CHAT_HELP.format(example=facts.cols[0].name))
        if talk.REPEAT.search(text) and convo.last:
            return convo.last
        if "health" in text or ("score" in text and not code):
            score = facts.health_score
            if SCORE_HOW.search(text):
                return Reply("sloth", lines.CHAT_SCORE_HOW.format(score=score))
            mood = "happy" if score > 80 else "grumpy" if score < 40 else "meh"
            return Reply("sloth", lines.CHAT_HEALTH.format(score=score, mood=lines.HEALTH_MOOD[mood]))
        if code:                               # about the generated Python: seed, libraries, the model, ...
            if not job.results:
                return Reply("coder", lines.CHAT_BUSY["coder"])
            who, body, choices = talk.code_answer(job.results, text)
            return self._say(convo, who, None, body, choices)

        cat = next((c for c, words in TOPICS.items() if any(w in text for w in words)), None)
        open_ended = cat in (None, "scribe")   # not a quality or chart question
        intent = "values" if open_ended and (VALUES.search(text) or COUNT.search(text)) else "profile"
        if open_ended and not STAT.search(text):
            if SAMPLE.search(text):
                return self._say(convo, "scribe", None, _sample_text(facts), ["what columns are there?"])
            if col is None and COLUMNS.search(text):
                return self._say(convo, "scribe", None, _columns_text(facts), [c.name for c in facts.cols[:MAX_CHOICES]])
            hit = _mentioned_value(facts, text, col) if COUNT.search(text) else None
            if hit:
                c, value, n = hit
                return self._say(convo, "scribe", c, f"{value!r} appears {n:,} times in {c.name} "
                                                     f"({n / max(1, facts.rows):.1%} of {facts.rows:,} rows).")
        if col is None:
            guesses = _fuzzy_columns(facts, text)
            if guesses:                        # "weather" could be weather_main or weather_description
                return self._ask(convo, cat or convo.cat or "scribe", guesses, None, facts, intent)
            if convo.col and FOLLOW_UP.search(text) and cat != "artist":
                col = convo.col                # "and what about it?"
        more = bool(MORE.search(text) and convo.cat)
        if cat is None and more:
            cat, col = convo.cat, col or convo.col
        elif cat is None and col:
            # Only a short follow-up ("total?", "and region?") keeps the last cat; "tell me about x" is a new ask.
            short = len(text.split()) <= 3 or FOLLOW_UP.search(text)
            cat = convo.cat if short and convo.cat in ("detective", "janitor") and intent == "profile" else "scribe"
        elif col and cat == "artist":          # "a chart of yield": the chart card about it, if there is one
            hit = talk.find_card(job.results, text, only="artist")
            if hit:
                return self._card_reply(convo, facts, *hit)
            cat = "scribe"
        elif col and cat not in ("detective", "janitor"):
            cat = "scribe"
        if col is None and STAT.search(text) and facts.measures:
            default = facts.focus or facts.measures[0]
            return self._ask(convo, "scribe", [default] + [c for c in facts.measures if c is not default], default, facts)
        if cat is None:                        # nothing obvious: maybe one of the cards is about it
            hit = talk.find_card(job.results, text)
            if hit:
                return self._card_reply(convo, facts, *hit)
            return Reply("sloth", lines.CHAT_HELP.format(example=facts.cols[0].name))
        if col is None and intent == "profile" and not more:
            hit = talk.find_card(job.results, text, only=cat)
            if hit:
                return self._card_reply(convo, facts, *hit)
        return self._reply(job, facts, convo, cat, col, more, intent)

    def _say(self, convo: Convo, cat: str, col: Col | None, text: str, choices: list[str] | None = None) -> Reply:
        """An answer straight from the facts or the code (no card needed), remembered for follow-ups."""
        convo.cat, convo.col = cat, col
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {text}", choices or [])

    def _card_reply(self, convo: Convo, facts: Facts, cat: str, card: dict) -> Reply:
        """Answer with one card: its title carries the headline number, its description says what it means."""
        convo.cat, convo.col = cat, None
        choices = _worst_columns(cat, facts)
        tip = f" {lines.CHAT_TAP}" if choices and cat in ("detective", "janitor") else ""
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {card['title']}. {card['description']}{tip}", choices)

    def _reply(self, job: Job, facts: Facts, convo: Convo, cat: str, col: Col | None, more: bool = False,
               intent: str = "profile") -> Reply:
        if intent == "values" and col and cat == "scribe":
            return self._say(convo, "scribe", col, _values_text(col, facts.rows))
        if cat not in job.results:
            return Reply(cat, lines.CHAT_FAILED if job.finished else lines.CHAT_BUSY[cat])
        convo.cat, convo.col = cat, col
        text = f"{lines.CHAT_VOICE[cat]} {answer(cat, facts, col, job.results[cat], more)}"
        choices = [] if col else _worst_columns(cat, facts)
        return Reply(cat, text + (f" {lines.CHAT_TAP}" if choices and cat != "scribe" else ""), choices)

    def _ask(self, convo: Convo, cat: str, options: list[Col], default: Col | None, facts: Facts,
             intent: str = "profile") -> Reply:
        """Ask the user to confirm or pick a column, and remember that we asked."""
        names = [c.name for c in options[:MAX_CHOICES]]
        if default is not None and len(options) > 1:     # stat question without a column
            why = "your target" if default is facts.target else "the main number column"
            body, choices = lines.CHAT_ASK_STAT.format(name=default.name, why=why), names
        elif len(options) == 1:
            body, choices = lines.CHAT_ASK_ONE.format(name=names[0]), ["yes", "no"]
        else:
            more = f" (+{len(options) - MAX_CHOICES} more)" if len(options) > MAX_CHOICES else ""
            body, choices = lines.CHAT_ASK_MANY.format(names=", ".join(names), more=more), names + ["all"]
        reply = Reply(cat, f"{lines.CHAT_VOICE[cat]} {body}", choices)
        convo.pending = Pending(cat, options, default if default is not None else (options[0] if len(options) == 1 else None),
                                reply, intent)
        return reply


def _resolve(pending: Pending, text: str, facts: Facts) -> tuple[str, Col | None]:
    """Read a message as the answer to a cat's question: ("col", c) | ("all", None) | ("no", None) | ("again", None) | ("new", None)."""
    t = text.strip(" .!?")
    if YES.fullmatch(t):
        return ("col", pending.default) if pending.default else ("again", None)
    if NO.fullmatch(t):
        return "no", None
    if t in ("all", "everything", "overall"):
        return "all", None
    col = _mentioned_column(facts, text)
    return ("col", col) if col else ("new", None)


def _fuzzy_columns(facts: Facts, text: str) -> list[Col]:
    """Columns that share a word with the message but are not named in full ("reading" -> reading_00, ...)."""
    topic_words = {w for words in TOPICS.values() for w in words}
    words = {w for w in re.findall(r"[a-z0-9]{4,}", text)
             if w not in CHAT_WORDS and not any(t in w or w in t for t in topic_words)}
    return [c for c in facts.cols if words & {t for t in re.split(r"\W|_", c.name.lower()) if len(t) >= 4}]


def _worst_columns(cat: str, facts: Facts) -> list[str]:
    """Columns worth a follow-up tap after a whole-file answer."""
    if cat == "detective":
        return [c for c, _ in sorted(facts.outlier_counts.items(), key=lambda kv: -kv[1])[:3]]
    if cat == "janitor":
        return [c.name for c in sorted(facts.cols, key=lambda c: -c.missing)[:3] if c.missing]
    if cat == "scribe":
        return ["what columns are there?", "show some rows"]
    return []


def _mentioned_column(facts: Facts, text: str) -> Col | None:
    """The longest column name the message mentions ("customer age" matches customer_age)."""
    for c in sorted(facts.cols, key=lambda c: -len(c.name)):
        for variant in {c.name.lower(), c.name.lower().replace("_", " ")}:
            if variant and re.search(rf"(?<!\w){re.escape(variant)}(?:e?s)?(?!\w)", text):
                return c
    return None


def _mentioned_value(facts: Facts, text: str, col: Col | None) -> tuple[Col, str, int] | None:
    """A text value from the data that the message names ("Labor Day"): (column, value, count). Longest wins."""
    best = None
    for c in ([col] if col else facts.cols):
        if c.kind != "text":
            continue
        for v, n in c.top:
            if len(v) >= 3 and re.search(rf"(?<!\w){re.escape(v.lower())}(?!\w)", text) and (best is None or len(v) > len(best[1])):
                best = (c, v, n)
    return best


def _values_text(col: Col, rows: int) -> str:
    """Every value of a column (up to VALUE_LINES), most common first, with counts."""
    shown = col.top[:VALUE_LINES]
    if not shown:
        return f"{col.name} is empty: {col.missing:,} of {rows:,} cells are missing."
    show = (lambda v: repr(v)) if col.kind == "text" else (lambda v: v)
    head = f"{col.name} has {col.distinct:,} distinct values"
    head += f" (the {len(shown)} most common):" if col.distinct > len(shown) else ":"
    body = "\n".join(f"{show(v)} ({n:,})" for v, n in shown)
    more = f"\n...and {col.distinct - len(shown):,} more." if col.distinct > len(shown) else ""
    gap = f"\n({col.missing:,} cells are missing.)" if col.missing else ""
    return f"{head}\n{body}{more}{gap}"


def _columns_text(facts: Facts) -> str:
    shown = [f"{c.name} ({c.kind})" for c in facts.cols[:40]]
    more = f", ...and {len(facts.cols) - 40} more" if len(facts.cols) > 40 else ""
    return f"{len(facts.cols)} columns: {', '.join(shown)}{more}."


def _sample_text(facts: Facts) -> str:
    cols = facts.cols[:8]
    rows = [f"row {i}: " + ", ".join(f"{c.name}={r[j] or '-'}" for j, c in enumerate(cols)) for i, r in enumerate(facts.head, 1)]
    note = f" (first {len(cols)} of {len(facts.cols)} columns)" if len(facts.cols) > len(cols) else ""
    return f"the first {len(rows)} rows{note}:\n" + "\n".join(rows)


def answer(cat: str, facts: Facts, col: Col | None, cards: list[dict], more: bool = False) -> str:
    """A cat's chat answer, from the facts (about one column) or its own cards."""
    if col and cat == "detective":
        if col.kind != "number":
            return f"{col.name} is not a number column, so no outliers to chase. It has {col.distinct:,} distinct values."
        n = facts.outlier_counts.get(col.name, 0)
        s = col.stats
        text = (f"{col.name} has {n:,} values outside the usual range "
                f"(more than 1.5x the IQR beyond {_fmt(s['q1'])} to {_fmt(s['q3'])}).") if n else \
               f"{col.name} looks clean: no values far outside {_fmt(s['q1'])} to {_fmt(s['q3'])}."
        if col.strays:
            text += f" It also has non-numbers like {', '.join(repr(v) for v in col.strays)}."
        rows = [e for e in facts.outlier_examples if e[1] == col.name][:3]
        if more and rows:
            text += " Most extreme: " + "; ".join(f"row {r[0]} = {_fmt(r[2])}" for r in rows) + "."
        return text
    if col and cat == "janitor":
        pct = col.missing / max(1, facts.rows) * 100
        return f"{col.name} has {col.missing:,} missing values ({pct:.1f}%). I would {_missing_action(col, pct)}."
    if col:
        return _profile_text(col, facts.rows)
    if cat == "scribe":
        return cards[0]["description"]
    titles = "; ".join(c["title"] for c in cards) or "nothing to report"
    if cat == "artist" and facts.pair:
        a, b, r, _, _ = facts.pair
        titles += f". The two columns that move together most: {a.name} and {b.name} (r = {r:.2f})"
    return f"{titles}. Open my results for the details."


def _profile_text(col: Col, rows: int) -> str:
    missing = f"{col.missing:,} of {rows:,} missing"
    s = col.stats
    if col.kind == "number" and s:
        return (f"{col.name} is a number column: min {_fmt(s['min'])}, median {_fmt(s['median'])}, "
                f"mean {_fmt(s['mean'])}, max {_fmt(s['max'])}; {missing}.")
    if col.kind == "date" and s:
        return f"{col.name} is a date column from {s['first']} to {s['last']}; {missing}."
    common = ", ".join(f"{v!r} ({n:,})" for v, n in col.top[:3]) or "none"
    return f"{col.name} is text with {col.distinct:,} distinct values; most common: {common}; {missing}."


def _missing_action(col: Col, pct: float) -> str:
    if pct > 40:
        return "drop column"
    return "fill with median" if col.kind == "number" else "fill with 'unknown'"


# ---------------------------------------------------------------- analysis


def analyse(info: FileInfo, selection: Selection | None = None) -> Facts:
    """Read every row of the file (minus the user's exclusions) and work out the facts the cats report."""
    sel = selection or Selection()
    keep = sel.columns if sel.columns is not None else list(range(len(info.columns)))
    rows: list[list[str]] = []
    excluded_rows = 0
    rules = [(j, _matcher(value)) for j, value in sel.exclude]
    row_ids: list[int] = []                    # each kept row's data row number in the file
    # shortcut: whole file held in memory; stream it in two passes if huge uploads matter.
    for i, raw in enumerate(iter_rows(info)):
        if i == 0:
            continue                           # header
        cells = [cell_text(raw[j]) if j < len(raw) else "" for j in range(len(info.columns))]
        if any(match(cells[j]) for j, match in rules):
            excluded_rows += 1
            continue
        rows.append([cells[j] for j in keep])
        row_ids.append(i)
    if not rows:
        raise ValueError("every row was excluded by the row filter")
    n = len(rows)
    width = len(keep)

    cols = [_profile(info.columns[j], [r[k] for r in rows]) for k, j in enumerate(keep)]
    index = {id(c): j for j, c in enumerate(cols)}
    measures = [c for c in cols if c.is_measure]
    groups = sorted((c for c in cols if c.kind == "text" and not _is_id(c.name) and 2 <= c.distinct <= 50),
                    key=lambda c: abs(c.distinct - 6))
    date_col = next((c for c in cols if c.kind == "date"), None)
    target_col = cols[keep.index(sel.target)] if sel.target in keep else None
    focus = target_col if target_col and target_col.is_measure else (measures[0] if measures else None)

    seen: dict[tuple, int] = {}
    duplicates = []
    for i, r in enumerate(rows):
        first = seen.setdefault(tuple(r), i)
        if first != i:
            duplicates.append((row_ids[first], row_ids[i]))
    del seen

    outlier_counts, examples, flagged = {}, [], set()
    for c in measures:
        s = c.stats
        if c.distinct <= 2 or not s:
            continue                           # flags and constants have no "usual range"
        iqr = s["q3"] - s["q1"]
        lo, hi = s["q1"] - 1.5 * iqr, s["q3"] + 1.5 * iqr
        hits = [i for i, x in enumerate(c.numbers) if x is not None and (x < lo or x > hi)]
        if hits:
            outlier_counts[c.name] = len(hits)
            flagged.update(hits)
            for i in hits:
                x = c.numbers[i]
                examples.append([row_ids[i], c.name, x, round((x - s["mean"]) / s["std"], 1) if s["std"] else 0.0])
    examples.sort(key=lambda e: -abs(e[3]))

    mixed = 0
    if date_col:
        j = index[id(date_col)]
        iso = sum(1 for r in rows if ISO_DATE.match(r[j]))
        other = sum(1 for r in rows if r[j].lower() not in NA and not ISO_DATE.match(r[j]))
        mixed = other if iso and other else 0

    by_group = None
    group = target_col if any(g is target_col for g in groups) else (groups[0] if groups else None)
    if group:
        j = index[id(group)]
        sums, counts = defaultdict(float), Counter()
        for i, r in enumerate(rows):
            if r[j].lower() in NA:
                continue
            x = focus.numbers[i] if focus else None
            if focus is None or x is not None:
                counts[r[j]] += 1
                sums[r[j]] += x or 0.0
        top = [(label, sums[label] / k if focus else k, k) for label, k in counts.most_common(MAX_BARS)]
        by_group = (group, sorted(top, key=lambda t: -t[1]))

    trend = []
    if date_col and focus:
        j = index[id(date_col)]
        months = defaultdict(float)
        for i, r in enumerate(rows):
            x = focus.numbers[i]
            if x is not None and ISO_DATE.match(r[j]):
                months[r[j][:7]] += x
        trend = sorted(months.items())[-36:]

    hist = _histogram(focus) if focus else None
    pair = _best_pair(measures)

    type_issues = [c for c in cols if c.kind == "number" and c.strays]
    missing_total = sum(c.missing for c in cols)
    rows_ = max(n, 1)
    # Each kind of problem can cost at most its cap, so one noisy check can't sink the score.
    score = (100 - min(40, missing_total / (rows_ * max(1, width)) * 300) - min(25, len(duplicates) / rows_ * 500)
             - min(25, len(flagged) / rows_ * 200) - min(20, 5 * len(type_issues)))

    for c in cols:
        c.numbers = []                         # facts are kept for chat; the raw values are not
    return Facts(
        filename=info.filename, rows=n, cols=cols, all_columns=len(info.columns),
        excluded=[(info.columns[j], v) for j, v in sel.exclude], excluded_rows=excluded_rows, measures=measures, groups=groups, date_col=date_col,
        target=target_col, focus=focus, missing_total=missing_total, duplicates=duplicates,
        outlier_counts=outlier_counts, outlier_examples=examples[:20], outlier_rows=len(flagged),
        type_issues=type_issues, mixed_dates=mixed, by_group=by_group, trend=trend, pair=pair, hist=hist,
        health_score=int(round(max(0, min(100, score)))), head=[[c[:40] for c in r] for r in rows[:5]],
    )


def _profile(name: str, values: list[str]) -> Col:
    present = [v for v in values if v.lower() not in NA]
    counts = Counter(present)
    numbers = [None if v.lower() in NA else _number(v) for v in values]
    parsed = [x for x in numbers if x is not None]
    kind = "text"
    if present and len(parsed) >= 0.9 * len(present):
        kind = "number"
    elif present and sum(1 for v in present if ISO_DATE.match(v) or OTHER_DATE.match(v)) >= 0.8 * len(present):
        kind = "date"

    stats, strays = {}, []
    if kind == "number":
        strays = [v for v, _ in Counter(v for v, x in zip(values, numbers)
                                        if x is None and v.lower() not in NA).most_common(3)]
        if len(parsed) >= 2:
            q1, median, q3 = statistics.quantiles(parsed, n=4, method="inclusive")
            stats = {"min": min(parsed), "max": max(parsed), "mean": statistics.fmean(parsed),
                     "median": median, "std": statistics.stdev(parsed), "q1": q1, "q3": q3}
    elif kind == "date":
        iso = [v[:10] for v in present if ISO_DATE.match(v)]
        if iso:
            stats = {"first": min(iso), "last": max(iso)}
    return Col(name=name, kind=kind, missing=len(values) - len(present), distinct=len(counts),
               example=present[0] if present else "", top=counts.most_common(TOP_VALUES), strays=strays,
               stats=stats, numbers=numbers if kind == "number" else [])


def _histogram(col: Col, bins: int = 10) -> tuple[list[str], list[int]] | None:
    xs = [x for x in col.numbers if x is not None]
    if not xs:
        return None
    lo, hi = min(xs), max(xs)
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int((x - lo) / width))] += 1
    return [f"{_fmt(lo + i * width)}-{_fmt(lo + (i + 1) * width)}" for i in range(bins)], counts


def _best_pair(measures: list[Col]):
    """The two measures that move together most (Pearson r on up to CORR_SAMPLE rows)."""
    cands = [c for c in measures if c.distinct > 2][:12]
    if len(cands) < 2:
        return None
    n = len(cands[0].numbers)
    step = max(1, n // CORR_SAMPLE)
    best = None
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            xy = [(x, y) for x, y in zip(a.numbers[::step], b.numbers[::step]) if x is not None and y is not None]
            try:
                r = statistics.correlation([x for x, _ in xy], [y for _, y in xy])
            except statistics.StatisticsError:
                continue                       # too few points, or a constant column
            if best is None or abs(r) > abs(best[2]):
                best = (a, b, r)
    if best is None:
        return None
    a, b, r = best
    xy = [[x, y] for x, y in zip(a.numbers, b.numbers) if x is not None and y is not None]
    points = [[round(x, 3), round(y, 3)] for x, y in xy[::max(1, len(xy) // SCATTER_POINTS)]]
    return a, b, r, points, step > 1


# ------------------------------------------------------------------ cards
# Every card follows the shape documented in engines/base.py.


def _loader(f: Facts) -> str:
    """`df = ...` plus the user's row filter and column choice."""
    name = f.filename.lower()
    na = f"keep_default_na=False, na_values={NA_VALUES!r}"
    read = (f"pd.read_excel({q(f.filename)}, {na})" if name.endswith(".xlsx")
            else f"pd.read_csv({q(f.filename)}{', sep=chr(9)' if name.endswith('.tsv') else ''}, {na})")
    code = f"df = {read}"
    for col, value in f.excluded:
        num = _number(value)
        code += (f"\ndf = df[pd.to_numeric(df[{q(col)}], errors=\"coerce\") != {num!r}]" if num is not None
                 else f"\ndf = df[df[{q(col)}].astype(str).str.strip() != {q(value)}]")
    if len(f.cols) < f.all_columns:
        code += f"\ndf = df[[{', '.join(q(c.name) for c in f.cols)}]]"
    return code


def detective_cards(f: Facts) -> list[dict]:
    rows = max(f.rows, 1)
    worst = sorted(f.outlier_counts.items(), key=lambda kv: -kv[1])[:MAX_BARS]
    num = f.focus.name if f.focus else (f.measures[0].name if f.measures else None)
    cards = [{
        "id": "detective-outliers",
        "title": f"{f.outlier_rows:,} suspicious rows",
        "description": ("Rows with at least one value far outside its column's usual range "
                        "(more than 1.5x the IQR beyond the middle half). Could be typos, could be real "
                        "extremes. Worth a look before modelling."
                        if f.measures else "No number columns, so there is no usual range to step outside of."),
        "severity": "warn" if f.outlier_rows else "ok",
        "chart": {"type": "hbar", "title": "Outliers per column", "x_label": "values", "y_label": "column",
                  "labels": [c for c, _ in worst], "values": [k for _, k in worst]} if worst else None,
        "table": {"columns": ["row", "column", "value", "z_score"], "rows": f.outlier_examples}
        if f.outlier_examples else None,
        "code": {"python": f"""import pandas as pd

{_loader(f)}
s = df[{q(num)}]
q1, q3 = s.quantile([0.25, 0.75])
iqr = q3 - q1
mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
print(mask.sum(), "suspicious rows")
df[mask].head()""", "r": None} if num else None,
    }]
    dupes = len(f.duplicates)
    cards.append({
        "id": "detective-duplicates",
        "title": f"{dupes:,} duplicate rows",
        "description": "Rows that are exact copies of an earlier row. Usually an export glitch; "
                       "they quietly inflate counts and averages.",
        "severity": "bad" if dupes > rows * 0.01 else "warn" if dupes else "ok",
        "chart": {"type": "bar", "title": "Unique vs duplicate rows", "x_label": "", "y_label": "rows",
                  "labels": ["unique", "duplicate"], "values": [f.rows - dupes, dupes]},
        "table": {"columns": ["first_seen_row", "duplicate_row"], "rows": [list(d) for d in f.duplicates[:200]]}
        if dupes else None,
        "code": {"python": """dupes = df[df.duplicated(keep="first")]
print(len(dupes), "duplicate rows")
df = df.drop_duplicates()""", "r": None},
    })
    bad = f.type_issues[0].name if f.type_issues else None
    cards.append({
        "id": "detective-types",
        "title": f"{len(f.type_issues)} columns with type problems",
        "description": "Columns that are mostly numbers but contain a few strays like 'N/A', '$3.50' or '?'. "
                       "pandas reads the whole column as text because of them.",
        "severity": "warn" if f.type_issues else "ok",
        "chart": None,
        "table": {"columns": ["column", "expected", "found", "examples"],
                  "rows": [[c.name, "number", "text", ", ".join(c.strays)] for c in f.type_issues]
                  or [["(none)", "", "", ""]]},
        "code": {"python": f"""bad = pd.to_numeric(df[{q(bad)}], errors="coerce").isna() & df[{q(bad)}].notna()
print(df.loc[bad, {q(bad)}].unique()[:10])
df[{q(bad)}] = pd.to_numeric(df[{q(bad)}].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")""",
                 "r": None} if bad else None,
    })
    return cards


def artist_cards(f: Facts) -> list[dict]:
    cards = []
    a = f.focus
    if a and f.hist:
        labels, counts = f.hist
        s = a.stats
        skew = ("right-skewed: most values are modest, a few are large" if s and s["mean"] > s["median"] + 0.1 * s["std"]
                else "left-skewed: a long tail of small values" if s and s["mean"] < s["median"] - 0.1 * s["std"]
                else "fairly symmetric around the middle")
        cards.append({
            "id": "artist-distribution",
            "title": f"Distribution of {a.name}",
            "description": f"A histogram, because {a.name} is one number per row. It is {skew} "
                           f"(median {_fmt(s['median'])}, mean {_fmt(s['mean'])})." if s else
                           f"A histogram, because {a.name} is one number per row.",
            "chart": {"type": "hist", "title": a.name, "x_label": a.name, "y_label": "count",
                      "labels": labels, "values": counts},
            "table": {"columns": ["bin", "count"], "rows": [[b, k] for b, k in zip(labels, counts)]},
            "code": {"python": f"""import matplotlib.pyplot as plt

df[{q(a.name)}].plot.hist(bins=10, edgecolor="black")
plt.xlabel({q(a.name)}); plt.ylabel("count")
plt.show()""", "r": None},
        })
    if f.by_group:
        g, top = f.by_group
        what = f"mean {a.name}" if a else "rows"
        cards.append({
            "id": "artist-by-category",
            "title": f"{what} by {g.name}",
            "description": f"A bar chart, because {g.name} has {g.distinct} categories"
                           f"{f' (top {MAX_BARS} shown)' if g.distinct > MAX_BARS else ''}. "
                           f"Sorted so the biggest bar is easy to spot: {top[0][0]!r} leads.",
            "chart": {"type": "bar", "title": f"{what} by {g.name}", "x_label": g.name, "y_label": what,
                      "labels": [t[0] for t in top], "values": [round(t[1], 2) for t in top]},
            "table": {"columns": [g.name, what, "rows"], "rows": [[t[0], round(t[1], 2), t[2]] for t in top]},
            "code": {"python": (f"""(df.groupby({q(g.name)})[{q(a.name)}].mean()
   .sort_values(ascending=False)
   .plot.bar(edgecolor="black"))
plt.show()""" if a else f"""df[{q(g.name)}].value_counts().plot.bar(edgecolor="black")
plt.show()"""), "r": None},
        })
    if a and f.date_col and len(f.trend) >= 2:
        d = f.date_col.name
        cards.append({
            "id": "artist-trend",
            "title": f"{a.name} over time",
            "description": f"A line chart of total {a.name} per month of {d}, "
                           f"from {f.trend[0][0]} to {f.trend[-1][0]}"
                           f"{' (last 36 months)' if len(f.trend) == 36 else ''}.",
            "chart": {"type": "line", "title": f"{a.name} per month", "x_label": "month", "y_label": a.name,
                      "labels": [m for m, _ in f.trend], "values": [round(v, 2) for _, v in f.trend]},
            "table": {"columns": ["month", a.name], "rows": [[m, round(v, 2)] for m, v in f.trend]},
            "code": {"python": f"""df[{q(d)}] = pd.to_datetime(df[{q(d)}], errors="coerce")
df.set_index({q(d)})[{q(a.name)}].resample("MS").sum().plot(marker="s")
plt.show()""", "r": None},
        })
    if f.pair:
        x, y, r, points, sampled = f.pair
        strength = "strongly" if abs(r) >= 0.7 else "moderately" if abs(r) >= 0.4 else "barely"
        cards.append({
            "id": "artist-scatter",
            "title": f"{x.name} vs {y.name}",
            "description": f"A scatter plot of the two number columns that move together most: "
                           f"{strength} {'up' if r >= 0 else 'opposite ways'} (r = {r:.2f}"
                           f"{', measured on a sample of rows' if sampled else ''}).",
            "chart": {"type": "scatter", "title": f"{x.name} vs {y.name}", "x_label": x.name, "y_label": y.name,
                      "points": points},
            "table": {"columns": [x.name, y.name], "rows": points},
            "code": {"python": f"""df.plot.scatter(x={q(x.name)}, y={q(y.name)}, s=8)
print(df[[{q(x.name)}, {q(y.name)}]].corr())
plt.show()""", "r": None},
        })
    return cards


def scribe_cards(f: Facts) -> list[dict]:
    kinds = Counter(c.kind for c in f.cols)
    cells = max(1, f.rows * len(f.cols))
    dictionary = [[c.name, c.kind, c.example, c.missing, c.distinct] for c in f.cols]
    notes = []
    if f.outlier_rows:
        notes.append(f"{f.outlier_rows:,} rows have extreme values; check them before averaging.")
    if f.type_issues:
        notes.append(f"{len(f.type_issues)} number columns contain text: {', '.join(c.name for c in f.type_issues[:5])}.")
    worst = sorted(f.cols, key=lambda c: -c.missing)
    if worst and worst[0].missing:
        notes.append(f"Missing values are worst in {worst[0].name} ({worst[0].missing / max(1, f.rows):.0%} empty).")
    if f.duplicates:
        notes.append(f"{len(f.duplicates):,} rows are exact duplicates.")
    if f.mixed_dates:
        notes.append(f"{f.mixed_dates:,} dates in {f.date_col.name} are not written as YYYY-MM-DD; parse them explicitly.")
    questions = []
    if f.target:
        questions.append(f"What predicts {f.target.name}?")
    if f.by_group and f.focus:
        questions.append(f"Which {f.by_group[0].name} drives {f.focus.name}?")
    if f.trend:
        questions.append(f"Is there a seasonal pattern in {f.focus.name}?")
    if f.pair:
        questions.append(f"Does {f.pair[0].name} explain {f.pair[1].name} (r = {f.pair[2]:.2f})?")
    if f.outlier_rows:
        questions.append("Which of the suspicious rows are data-entry mistakes?")
    return [
        {
            "id": "scribe-summary",
            "title": "The data in one paragraph",
            "description": (
                f"{f.filename} has {f.rows:,} rows and {len(f.cols)} columns: {kinds['number']} hold numbers, "
                f"{kinds['date']} hold dates and {kinds['text']} hold text or categories. "
                f"{f.missing_total:,} cells are empty ({f.missing_total / cells:.1%}) and "
                f"{len(f.duplicates):,} rows are repeated. Data health: {f.health_score}/100."
                + (f" You left out {f.all_columns - len(f.cols)} of {f.all_columns} columns." if len(f.cols) < f.all_columns else "")
                + (f" Your filter dropped {f.excluded_rows:,} rows." if f.excluded else "")
            ),
            "severity": "ok",
            "chart": None,
            "table": {"columns": ["column", "type", "example", "missing", "distinct"], "rows": dictionary},
        },
        {
            "id": "scribe-watch-out",
            "title": "Things to watch out for",
            "description": "\n".join(f"{i}) {n}" for i, n in enumerate(notes, 1)) or "Nothing worrying. Suspiciously tidy.",
            "severity": "warn" if notes else "ok",
            "chart": None,
        },
        {
            "id": "scribe-next",
            "title": "Questions this data could answer",
            "description": "\n".join(f"{i}) {n}" for i, n in enumerate(questions, 1)) or "Add a number column and ask again.",
            "chart": None,
        },
    ]


def coder_cards(f: Facts) -> list[dict]:
    cards = [{
        "id": "coder-load",
        "title": "Load and peek",
        "description": "Read the file and get a first look at shape, types and missing values.",
        "chart": None,
        "code": {"python": f"""import pandas as pd

{_loader(f)}
print(df.shape)          # ({f.rows}, {len(f.cols)})
print(df.dtypes)
print(df.isna().sum().sort_values(ascending=False).head(10))
df.head()""", "r": None},
    }]
    g = f.by_group[0].name if f.by_group else None
    num = f.focus.name if f.focus else None
    summary = 'summary = df.describe(include="number").T\nsummary["missing"] = df.isna().sum()\nprint(summary.round(2))'
    if g:
        summary += f"\n\nprint(df[{q(g)}].value_counts().head(10))"
        if num:
            summary += f'\nprint(df.groupby({q(g)})[{q(num)}].agg(["count", "mean", "median"]).round(2))'
    cards.append({"id": "coder-summary", "title": "Summary statistics",
                  "description": "describe() for numbers, value_counts() for the main category.",
                  "chart": None, "code": {"python": summary, "r": None}})

    target = f.target or (f.measures[-1] if f.measures else None)
    if target:
        classify = target.kind != "number"
        model = "LogisticRegression(max_iter=1000)" if classify else "LinearRegression()"
        cards.append({
            "id": "coder-baseline",
            "title": "Baseline model",
            "description": (f"A quick {'classification' if classify else 'linear-regression'} baseline predicting "
                            f"{target.name}{'' if f.target else ' (no target picked, so the last number column)'}. "
                            "Not fancy, but it tells you whether a fancier model is worth the effort."),
            "chart": None,
            "code": {"python": f"""from sklearn.compose import make_column_transformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import {model.split('(')[0]}
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

df = df.dropna(subset=[{q(target.name)}])
X = df.drop(columns=[{q(target.name)}])
y = df[{q(target.name)}]
num_cols = X.select_dtypes("number").columns
cat_cols = X.select_dtypes(exclude="number").columns

prep = make_column_transformer(
    (SimpleImputer(strategy="median"), num_cols),
    (make_pipeline(SimpleImputer(strategy="most_frequent"),
                   OneHotEncoder(handle_unknown="ignore")), cat_cols),
)
model = make_pipeline(prep, {model})

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model.fit(X_train, y_train)
print("{'accuracy' if classify else 'R^2'}:", round(model.score(X_test, y_test), 3))""", "r": None},
        })
    return cards


def janitor_cards(f: Facts) -> list[dict]:
    rows = max(f.rows, 1)
    by_missing = sorted(f.cols, key=lambda c: -c.missing)
    shown = [c for c in by_missing if c.missing][:MAX_BARS]
    plan = [[c.name, c.missing, round(c.missing / rows * 100, 1), _missing_action(c, c.missing / rows * 100)]
            for c in by_missing if c.missing]
    text_cols = [c for c in f.cols if c.kind == "text" and not _is_id(c.name)]
    encode = [[c.name, c.distinct, "one-hot" if c.distinct <= 12 else "frequency / target encoding"]
              for c in sorted(text_cols, key=lambda c: c.distinct)]
    g = (f.groups[0] if f.groups else text_cols[0] if text_cols else None)
    deduped = f.rows - len(f.duplicates)
    fix = [c.name for c in f.type_issues]
    fix_code = "".join(f"""
    df[{q(c)}] = pd.to_numeric(
        df[{q(c)}].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")""" for c in fix)
    stem = f.filename.rsplit(".", 1)[0]
    return [
        {
            "id": "janitor-missing",
            "title": f"{f.missing_total:,} missing values",
            "description": "Empty cells per column, with what I would do about each. "
                           "Numbers get the median (robust to outliers), text gets 'unknown', "
                           "columns more than 40% empty get dropped.",
            "severity": "bad" if f.missing_total > rows * 0.1 else "warn" if f.missing_total else "ok",
            "chart": {"type": "hbar", "title": "% missing per column", "x_label": "% missing", "y_label": "column",
                      "labels": [c.name for c in shown], "values": [round(c.missing / rows * 100, 1) for c in shown]}
            if shown else None,
            "table": {"columns": ["column", "missing", "percent", "action"],
                      "rows": plan or [["(none)", 0, 0, "nothing to do"]]},
            "code": {"python": """num_cols = df.select_dtypes("number").columns
txt_cols = df.columns.difference(num_cols)
df[num_cols] = df[num_cols].fillna(df[num_cols].median())
df[txt_cols] = df[txt_cols].fillna("unknown")""", "r": None},
        },
        {
            "id": "janitor-encoding",
            "title": "Encoding the categories",
            "description": "Text columns need to become numbers before most models will eat them. "
                           "Few categories: one-hot. Lots of categories: frequency encoding.",
            "chart": {"type": "bar", "title": "distinct values per text column", "x_label": "column",
                      "y_label": "distinct", "labels": [r[0] for r in encode[:MAX_BARS]],
                      "values": [r[1] for r in encode[:MAX_BARS]]} if encode else None,
            "table": {"columns": ["column", "distinct_values", "strategy"], "rows": encode or [["(none)", 0, ""]]},
            "code": {"python": f"""df[{q(g.name)}] = df[{q(g.name)}].str.strip().str.lower()
df = pd.get_dummies(df, columns=[{q(g.name)}], prefix={q(g.name)}, dtype=int)""", "r": None} if g else None,
        },
        {
            "id": "janitor-recipe",
            "title": "Full cleaning recipe",
            "description": "Everything above in one function, in a safe order: dedupe, fix types, fill gaps, trim text.",
            "chart": None,
            "table": {"columns": ["step", "rows_before", "rows_after"],
                      "rows": [["drop duplicates", f.rows, deduped],
                               ["fix types", deduped, deduped],
                               ["fill missing", deduped, deduped]]},
            "code": {"python": f"""def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates().copy(){fix_code}
    num_cols = df.select_dtypes("number").columns
    txt_cols = df.columns.difference(num_cols)
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    df[txt_cols] = df[txt_cols].fillna("unknown").apply(lambda s: s.astype(str).str.strip())
    return df

df_clean = clean(df)
df_clean.to_csv({q(stem + '_clean.csv')}, index=False)""", "r": None},
        },
    ]


BUILDERS = {
    "detective": detective_cards,
    "artist": artist_cards,
    "scribe": scribe_cards,
    "coder": coder_cards,
    "janitor": janitor_cards,
}
