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
from dataclasses import dataclass, field, replace

from ..cats import CAT_IDS, paper_total, split_papers
from ..files import FileInfo, Selection, cell_text, iter_rows
from ..files import cell_matcher as _matcher
from ..files import parse_number as _number
from ..jobs import Job
from . import lines, rcode, talk
from .base import Engine, Reply

# Cells that count as missing (compared lower-cased). "None" is deliberately not here:
# it is often a real answer ("no holiday"), so it stays an ordinary value.
NA = {"", "na", "n/a", "nan", "null", "#n/a", "<na>"}
# The same list for pandas; keep_default_na=False stops it adding "None" back.
NA_VALUES = ["", "NA", "N/A", "NaN", "nan", "null", "NULL", "n/a", "#N/A", "<NA>"]
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
OTHER_DATE = re.compile(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}$")
CORR_SAMPLE = 5000  # rows used to rank column pairs by correlation
SCATTER_POINTS = 300
MAX_BARS = 10
BOX_OUTLIERS = 200  # outlier dots sent to the box plot (the most extreme distinct values); the table keeps the count
HEAT_MAX = 10  # number columns drawn in the correlation heatmap
HIST_BINS = 10  # the baseline histogram; the bins dropdown offers 2 to MAX_HIST_BINS
MAX_HIST_BINS = 100
BIN_CHOICES = (5, 10, 15, 20, 30, 40, 50, 75, 100)  # the distribution card's bins dropdown
TOP_VALUES = 50  # most common values kept per column, for chat answers
VALUE_LINES = 30  # values listed in one chat answer

q = json.dumps  # a column or file name as a Python string literal

# Chat: words that make a message a follow-up ("what about it?"), a request for detail, or a stat question.
FOLLOW_UP = re.compile(
    r"\b(it|its|that|those|them|same)\b|^\s*(and|also|what about|how about|why)\b"
)
MORE = re.compile(r"\b(more|details?|examples?|show me|which rows)\b")
SCORE_HOW = re.compile(
    r"\b(how|why|calculat\w*|comput\w*|formula|mean|made|work|measure\w*|based)\b"
)
STAT = re.compile(
    r"\b(mean|average|median|min|minimum|max|maximum|highest|lowest|biggest|smallest|cheapest|priciest|"
    r"most expensive|youngest|typical|typically|usual|usually)\b"
)
YES = re.compile(r"(yes|yeah|yep|yup|ok|okay|sure|y|please|do it|go ahead)( please)?")
NO = re.compile(r"(no|nope|nah|n|cancel|never ?mind|forget it)")
# Words that are not column hints when matching part of a column name.
CHAT_WORDS = {
    "show",
    "tell",
    "with",
    "from",
    "have",
    "that",
    "this",
    "what",
    "does",
    "data",
    "about",
    "there",
    "which",
    "where",
    "give",
    "find",
    "look",
    "check",
    "please",
    "dataset",
    "file",
    "column",
    "columns",
}
MAX_CHOICES = 6
HELP_HINT = lines.CHAT_HELP.split('{', maxsplit=1)[0]
# Which numbers a question asks for, so "the highest temp" gets the max and not the whole profile.
WANTED = [
    (stat, re.compile(words))
    for stat, words in (
        ("mode", r"most (common|frequent|popular)|\bmode\b"),
        ("rare", r"least (common|frequent|popular)|\brarest\b"),
        (
            "min",
            r"\b(min|minimum|lowest|smallest|earliest|oldest|cheapest|youngest|fewest)\b",
        ),
        (
            "max",
            r"\b(max|maximum|highest|largest|biggest|greatest|latest|newest|peak|priciest|most expensive)\b",
        ),
        ("range", r"\brange\b"),
        ("mean", r"\b(mean|average|avg|typical|typically|usual|usually)\b"),
        ("median", r"\b(median|typical|typically|usual|usually)\b"),
        ("std", r"\b(std|standard deviation|spread|variance)\b"),
        ("quartiles", r"\b(quartiles?|iqr|percentiles?)\b"),
        ("sum", r"\bsum\b"),
    )
]
STAT_LABEL = {
    "mode": "most common value",
    "rare": "least common value",
    "min": "lowest value",
    "max": "highest value",
    "range": "range",
    "mean": "mean",
    "median": "median",
    "std": "spread",
    "quartiles": "quartiles",
    "sum": "sum",
}
# Questions about what is in the data (the scribe answers them from the facts).
SAMPLE = re.compile(
    r"\b(sample|first (few )?rows?|top rows?|few rows|some rows|head|preview|example rows?|look like|"
    r"peek|glimpse|(few|some) lines)\b"
    r"|\bshow (me )?(the )?(data|rows|dataset)\b"
)
COLUMNS = re.compile(r"\b(columns?|fields?|headers?|variables?)\b")
COUNT = re.compile(r"\b(how many|count|number of|how often)\b")
OTHER_COLUMN = re.compile(r"\b(the )?(other|another|different) (column|one)\b")
# "use 30 bins", "change the scatter to temp vs rain", "show a box plot of rain": the chart cards' dropdowns do that.
# A question ("what are the limits of too many bins?") is not a request, so it never matches.
CHART_EDIT = re.compile(
    r"^(?!\s*(what|why|how|when|which|is|are|does|do|should|would)\b)(?:"
    r".*\b\d+\s*(bins?|buckets?|bars)\b"
    r"|.*\b(change|switch|make|use|set|redraw|re-draw|swap|turn|convert|rename|more|fewer|less)\b.*"
    r"\b(histograms?|distributions?|charts?|plots?|graphs?|scatter\w*|box ?plots?|heat ?maps?|axis|axes|title|"
    r"labels?|bins?|buckets?)\b"
    r"|.*\bshow (me )?(the |a )?(histogram|distribution|box ?plot|scatter\w*) (of|for)\b)"
)
VALUES = re.compile(
    r"\b(list|unique|distinct|different|categories|category|kinds?|options|values|names?)\b"
    r"|\b(what|which)\b[^?]*\b(are there|is there|exist|exists|appear|appears|are in|are included|do we have|do you have)\b"
)

# Code questions are matched separately (talk.CODE) because they need whole words.
TOPICS: dict[str, tuple[str, ...]] = {  # checked in this order
    "detective": (
        "outlier",
        "suspicious",
        "extreme",
        "duplicate",
        "dupe",
        "type problem",
        "dtype",
        "data type",
        "weird",
        "wrong",
        "strange",
        "fishy",
        "odd",
        "unusual",
        "anomal",
        "repeated",
        "twice",
    ),
    "artist": (
        "chart",
        "plot",
        "graph",
        "visual",
        "histogram",
        "distribution",
        "trend",
        "correlat",
        "scatter",
        "relationship",
        "together",
    ),
    "janitor": (
        "missing",
        "clean",
        "empty",
        "null",
        "blank",
        "fill",
        "encod",
        "preprocess",
        "impute",
        "gaps",
        "holes",
    ),
    "scribe": (
        "summary",
        "summar",
        "explain",
        "describe",
        "overview",
        "column",
        "row",
        "how many",
        "mean",
        "average",
        "median",
        "min",
        "max",
        "inside",
        "contain",
        "dataset",
    ),
}


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def _is_id(name: str) -> bool:
    return bool(re.search(r"(^|_)(id|index|key)$", name.lower()))


@dataclass
class Col:
    name: str
    kind: str  # "number" | "date" | "text"
    missing: int
    distinct: int
    example: str
    top: list[tuple[str, int]]  # most common values, most common first
    strays: list[str]  # non-numbers in a number column
    stats: dict = field(
        default_factory=dict
    )  # number: min/max/mean/median/std/q1/q3, date: first/last
    numbers: list[float | None] = field(
        default_factory=list, repr=False
    )  # per row, number columns only

    @property
    def is_measure(self) -> bool:
        return self.kind == "number" and not _is_id(self.name)


@dataclass
class Facts:
    filename: str
    rows: int  # after the user's row filter
    cols: list[Col]  # the chosen columns
    all_columns: int  # columns in the file
    excluded: list[tuple[str, str]]  # (column, value) rules the user set
    excluded_rows: int
    measures: list[Col]
    groups: list[Col]  # text columns with a handful of categories
    date_col: Col | None
    target: Col | None
    focus: Col | None  # the measure the charts are about
    missing_total: int
    duplicates: list[
        tuple[int, int]
    ]  # (first_seen_row, duplicate_row), 1-based data rows
    outlier_counts: dict[str, int]
    outlier_examples: list[list]  # [row, column, value, z]
    outlier_rows: int
    flat: list[str]  # number columns whose middle half is one value, so the IQR rule cannot judge them
    type_issues: list[Col]
    mixed_dates: int  # date cells not written as YYYY-MM-DD
    by_group: (
        tuple[Col, list[tuple[str, float, int]]] | None
    )  # group col, [(label, mean or count, n)]
    trend: list[tuple[str, float]]  # (YYYY-MM, sum of focus)
    pair: (
        tuple[Col, Col, float, list[list[float]], bool] | None
    )  # a, b, r, points, sampled
    corr: list[tuple[str, str, float]]  # every measure pair (a, b, r), strongest first
    hist: tuple[list[str], list[int]] | None
    box: dict | None
    health_score: int
    head: list[list[str]]  # the first kept rows, in the order of `cols`
    encoding: str = "utf-8-sig"  # how the file was decoded; the exported code must read it the same way
    deduped: bool = False  # repeated column names were renamed (amount, amount.1)


@dataclass
class Pending:
    """A question a cat asked and is waiting on."""

    cat: str
    options: list[Col]
    default: Col | None  # what "yes" means; None when there are several equal guesses
    ask: Reply  # repeated if the user answers with just "yes" to a list
    intent: str = "profile"  # "values" when the user asked to list a column's values
    wanted: tuple[
        str, ...
    ] = ()  # the stats asked for ("max", ...), kept while the cat checks the column


@dataclass
class Convo:
    """What the cats remember about one job's chat: the last cat and column, and any open question."""

    cat: str | None = None
    col: Col | None = None
    pending: Pending | None = None
    last: list[Reply] | None = None  # the last answer, for "say that again"
    history: list[tuple[str, str]] = field(
        default_factory=list
    )  # the last few (question, answer), for a language model
    known: set[str] = field(
        default_factory=set
    )  # words from this file's columns and values, for typo fixes


# ------------------------------------------------------------------ engine


class LocalEngine(Engine):
    name = "local"

    def __init__(self, speed: float = 1.0) -> None:
        self.speed = speed
        self._facts: dict[str, Facts] = {}  # job id -> facts, for chat
        self._convo: dict[str, Convo] = {}

    async def run(self, job: Job) -> None:
        info = job.file
        for cat, count in split_papers(paper_total(info.rows)).items():
            await job.emit("delegated", cat=cat, paper_count=count)

        # Read the file while the papers fly to the desks.
        facts, _ = await asyncio.gather(
            asyncio.to_thread(analyse, info, job.selection),
            asyncio.sleep(2.5 * self.speed),
        )
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
        await asyncio.gather(
            *(
                self._run_cat(
                    job, cat, cards[cat], done_vars, random.Random(rng.random())
                )
                for cat in CAT_IDS
            )
        )
        await job.emit("done", health_score=facts.health_score)

    async def _run_cat(
        self,
        job: Job,
        cat: str,
        cards: list[dict] | Exception,
        done_vars: dict,
        rng: random.Random,
    ) -> None:
        duration = rng.uniform(4, 10) * self.speed
        steps = lines.PROGRESS_LINES[cat]
        percent = 0
        await job.emit("progress", cat=cat, percent=0, message=steps[0])
        while percent < 100:
            step = rng.randint(6, 14)
            await asyncio.sleep(duration * step / 100)
            percent = min(100, percent + step)
            if isinstance(cards, Exception) and percent >= 50:
                await job.emit(
                    "error",
                    cat=cat,
                    message=f"tripped over this file ({type(cards).__name__}: {cards})",
                )
                return
            await job.emit(
                "progress",
                cat=cat,
                percent=percent,
                message=steps[min(len(steps) - 1, percent * len(steps) // 100)],
            )
        await job.emit(
            "progress",
            cat=cat,
            percent=100,
            message=lines.DONE_LINES[cat].format(**done_vars),
        )
        await job.emit("result", cat=cat, cards=cards)

    # ----------------------------------------------------------------- chat

    async def chat(self, job: Job | None, message: str) -> Reply:
        await asyncio.sleep(0.6 * self.speed)  # sloths reply slowly
        if job is None:
            return await self._no_file(message)
        replies: list[Reply] = []
        for question in talk.split_questions(message):
            for reply in _as_list(await self._answer(job, question)):
                if any(r.text == reply.text for r in replies):
                    continue  # two vague questions, one hint is enough
                if replies and reply.who == replies[-1].who != "sloth":
                    voice = (
                        f"{lines.CHAT_VOICE[reply.who]} "  # same cat again: say it once
                    )
                    reply = replace(reply, text=reply.text.removeprefix(voice))
                replies.append(reply)
        if any(
            r.who != "sloth" for r in replies
        ):  # the "ask about..." hint is only for when no cat answered
            replies = [r for r in replies if not r.text.startswith(HELP_HINT)]
        if job.id in self._convo:
            convo = self._convo[job.id]
            convo.last = replies
            convo.history = (
                convo.history
                + [(message[:300], " ".join(r.text for r in replies)[:400])]
            )[-3:]
        return replies

    async def _no_file(self, message: str) -> list[Reply]:
        """Nothing to ask about yet: one hint, however many questions."""
        return [Reply("sloth", random.choice(lines.CHAT_NO_JOB))]

    async def _answer(self, job: Job, question: str) -> Reply | list[Reply]:
        """One question. Async so an engine that asks a language model can await it (see gemma.py)."""
        return self._chat(job, question)

    def _normalise(self, facts: Facts, convo: Convo, message: str) -> str:
        if not convo.known:
            convo.known = {
                w
                for c in facts.cols
                for w in re.split(r"[\W_]+", c.name.lower())
                if len(w) >= 3
            }
            convo.known |= {
                w
                for c in facts.cols
                if c.kind == "text"
                for v, _ in c.top
                for w in re.findall(r"[a-z]{3,}", v.lower())
            }
        return talk.normalise(message, convo.known)

    def _chat(self, job: Job | None, message: str) -> Reply | list[Reply]:
        """Read a message in this order: an open question, small talk, health, code, what is inside the data
        (columns, rows, values), a column or topic for one cat, and last any card that matches."""
        if job is None:
            return Reply("sloth", random.choice(lines.CHAT_NO_JOB))
        facts = self._facts.get(job.id)
        if facts is None:
            return Reply("sloth", lines.CHAT_NOT_READY)
        convo = self._convo.setdefault(job.id, Convo())
        text = self._normalise(facts, convo, message)

        # A cat asked something last turn: this message may be the answer.
        pending, convo.pending = convo.pending, None
        if pending:
            kind, col = _resolve(pending, text, facts)
            if kind == "no":
                return Reply("sloth", lines.CHAT_NEVERMIND)
            if kind == "again":
                convo.pending = pending
                return replace(pending.ask, followup=True)
            if kind != "new":
                answer_ = self._reply(
                    job,
                    facts,
                    convo,
                    pending.cat,
                    col,
                    intent=pending.intent,
                    wanted=pending.wanted,
                )
                return replace(answer_, followup=True)

        mentions = _mentioned_columns(facts, text)
        cols = [c for c, _, _ in mentions]
        col = cols[0] if cols else None
        code = talk.CODE.search(text)
        if code and any(code.group(0) in c.name.lower() for c in cols):
            code = None  # "zip code" can be a column
        small = talk.small_talk(text)
        if small:
            return Reply("sloth", small)
        if talk.HELP.search(text) or text.strip(" ?!.") == "help":
            return Reply("sloth", lines.CHAT_HELP.format(example=facts.cols[0].name))
        if talk.REPEAT.search(text) and convo.last:
            return list(convo.last)
        if CHART_EDIT.search(text) and not code:
            return self._say(convo, "artist", None, lines.CHAT_CHART_DIY)
        if "health" in text or ("score" in text and not code):
            score = facts.health_score
            if SCORE_HOW.search(text):
                return Reply("sloth", lines.CHAT_SCORE_HOW.format(score=score))
            mood = "happy" if score > 80 else "grumpy" if score < 40 else "meh"
            return Reply(
                "sloth",
                lines.CHAT_HEALTH.format(score=score, mood=lines.HEALTH_MOOD[mood]),
            )
        if code:  # about the generated Python: seed, libraries, the model, ...
            if not job.results:
                return Reply("coder", lines.CHAT_BUSY["coder"])
            who, body, choices, snippet = talk.code_answer(job.results, text)
            return replace(self._say(convo, who, None, body, choices), code=snippet)

        cat = next(
            (c for c, words in TOPICS.items() if any(w in text for w in words)), None
        )
        open_ended = cat in (None, "scribe")  # not a quality or chart question
        intent = (
            "values"
            if open_ended and (VALUES.search(text) or COUNT.search(text))
            else "profile"
        )
        wanted = _wanted(text)
        if col is None and OTHER_COLUMN.search(text):
            options = [
                c
                for c in (facts.measures if convo.cat == "detective" else facts.cols)
                if c is not convo.col
            ]
            if len(options) == 1:
                col = options[0]
            else:
                return self._ask(
                    convo,
                    convo.cat if convo.cat in ("detective", "janitor") else "scribe",
                    options,
                    None,
                    facts,
                    intent,
                    wanted,
                )
        if open_ended and not STAT.search(text):
            # "how many rows have snow?" names a column: not the row total (the cat asks which column below)
            if (
                COUNT.search(text)
                and col is None
                and re.search(r"\brows?\b", text)
                and not _fuzzy_columns(facts, text)
            ):
                left_out = (
                    f" ({facts.excluded_rows:,} more were left out by your filter)"
                    if facts.excluded_rows
                    else ""
                )
                return self._say(
                    convo, "scribe", None, f"{facts.rows:,} rows{left_out}."
                )
            if COUNT.search(text) and col is None and COLUMNS.search(text):
                return self._say(
                    convo,
                    "scribe",
                    None,
                    f"{len(facts.cols)} columns.",
                    ["what columns are there?"],
                )
            if SAMPLE.search(text):
                return self._say(
                    convo,
                    "scribe",
                    None,
                    _sample_text(facts),
                    ["what columns are there?"],
                )
            if col is None and COLUMNS.search(text):
                return self._say(
                    convo,
                    "scribe",
                    None,
                    _columns_text(facts),
                    [c.name for c in facts.cols[:MAX_CHOICES]],
                )
            hit = _mentioned_value(facts, text, col) if COUNT.search(text) else None
            if hit:
                c, value, n = hit
                return self._say(
                    convo,
                    "scribe",
                    c,
                    f"{value!r} appears {n:,} times in {c.name} "
                    f"({n / max(1, facts.rows):.1%} of {facts.rows:,} rows).",
                )
        if len(cols) > 1 and cat in (None, "scribe", "detective", "janitor"):
            # "highest temp and lowest rain": each column gets the stats named next to it, or all of them
            return [
                self._reply(
                    job,
                    facts,
                    convo,
                    cat or "scribe",
                    c,
                    intent=intent,
                    wanted=_wanted(text, lo, end) or wanted,
                )
                for (c, _, end), lo in zip(mentions, [0] + [e for _, _, e in mentions])
            ]
        if col is None:
            guesses = _fuzzy_columns(facts, text)
            if guesses:  # "weather" could be weather_main or weather_description
                asker = cat or (
                    convo.cat if convo.cat in ("detective", "janitor") else "scribe"
                )  # never the coder
                return self._ask(convo, asker, guesses, None, facts, intent, wanted)
            if convo.col and FOLLOW_UP.search(text) and cat != "artist":
                col = convo.col  # "and what about it?"
        more = bool(MORE.search(text) and convo.cat)
        if cat is None and more:
            cat, col = convo.cat, col or convo.col
        elif cat is None and col:
            # Only a short follow-up ("total?", "and region?") keeps the last cat; "tell me about x" is a new ask.
            short = len(text.split()) <= 3 or FOLLOW_UP.search(text)
            keep = (
                short
                and convo.cat in ("detective", "janitor")
                and intent == "profile"
                and not wanted
            )
            cat = convo.cat if keep else "scribe"
        elif (
            col and cat == "artist"
        ):  # "a chart of yield": the chart card about it, if there is one
            hit = talk.find_card(job.results, text, only="artist")
            if hit:
                return self._card_reply(convo, facts, *hit)
            cat = "scribe"
        elif col and cat not in ("detective", "janitor"):
            cat = "scribe"
        if col is None and STAT.search(text) and facts.measures:
            default = facts.focus or facts.measures[0]
            return self._ask(
                convo,
                "scribe",
                [default] + [c for c in facts.measures if c is not default],
                default,
                facts,
                wanted=wanted,
            )
        if cat is None:  # nothing obvious: maybe one of the cards is about it
            hit = talk.find_card(job.results, text)
            if hit:
                return self._card_reply(convo, facts, *hit)
            return Reply("sloth", lines.CHAT_HELP.format(example=facts.cols[0].name))
        if col is None and intent == "profile" and not more:
            hit = talk.find_card(job.results, text, only=cat)
            if hit:
                return self._card_reply(convo, facts, *hit)
        return self._reply(job, facts, convo, cat, col, more, intent, wanted)

    def _say(
        self,
        convo: Convo,
        cat: str,
        col: Col | None,
        text: str,
        choices: list[str] | None = None,
    ) -> Reply:
        """An answer straight from the facts or the code (no card needed), remembered for follow-ups."""
        convo.cat, convo.col = cat, col
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {text}", choices or [])

    def _card_reply(self, convo: Convo, facts: Facts, cat: str, card: dict) -> Reply:
        """Answer with one card: its title carries the headline number, its description says what it means."""
        convo.cat, convo.col = cat, None
        # Column buttons only where they lead on from this card (outliers -> per column), not after every answer.
        choices = (
            _worst_columns(cat, facts)
            if card["id"] in ("detective-outliers", "janitor-missing", "scribe-summary")
            else []
        )
        tip = (
            f" {lines.CHAT_TAP}" if choices and cat in ("detective", "janitor") else ""
        )
        return Reply(
            cat,
            f"{lines.CHAT_VOICE[cat]} {card['title']}. {card['description']}{tip}",
            choices,
        )

    def _reply(
        self,
        job: Job,
        facts: Facts,
        convo: Convo,
        cat: str,
        col: Col | None,
        more: bool = False,
        intent: str = "profile",
        wanted: tuple[str, ...] = (),
    ) -> Reply:
        if intent == "values" and col and cat == "scribe":
            return self._say(convo, "scribe", col, _values_text(col, facts.rows))
        if cat not in job.results:
            return Reply(
                cat, lines.CHAT_FAILED if job.finished else lines.CHAT_BUSY[cat]
            )
        convo.cat, convo.col = cat, col
        text = f"{lines.CHAT_VOICE[cat]} {answer(cat, facts, col, job.results[cat], more, wanted)}"
        choices = [] if col else _worst_columns(cat, facts)
        return Reply(
            cat,
            text + (f" {lines.CHAT_TAP}" if choices and cat != "scribe" else ""),
            choices,
        )

    def _ask(
        self,
        convo: Convo,
        cat: str,
        options: list[Col],
        default: Col | None,
        facts: Facts,
        intent: str = "profile",
        wanted: tuple[str, ...] = (),
    ) -> Reply:
        """Ask the user to confirm or pick a column, and remember that we asked."""
        names = [c.name for c in options[:MAX_CHOICES]]
        if default is not None and len(options) > 1:  # stat question without a column
            why = "your target" if default is facts.target else "the main number column"
            body, choices = (
                lines.CHAT_ASK_STAT.format(name=default.name, why=why),
                names,
            )
        elif len(options) == 1:
            body, choices = lines.CHAT_ASK_ONE.format(name=names[0]), ["yes", "no"]
        else:
            more = (
                f" (+{len(options) - MAX_CHOICES} more)"
                if len(options) > MAX_CHOICES
                else ""
            )
            body, choices = (
                lines.CHAT_ASK_MANY.format(names=", ".join(names), more=more),
                names + ["all"],
            )
        reply = Reply(cat, f"{lines.CHAT_VOICE[cat]} {body}", choices)
        convo.pending = Pending(
            cat,
            options,
            default
            if default is not None
            else (options[0] if len(options) == 1 else None),
            reply,
            intent,
            wanted,
        )
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
    if any(w in t for cat in ("detective", "artist", "janitor") for w in TOPICS[cat]):
        return (
            "new",
            None,
        )  # "any holes in the ratings" is a new question, not just a column name
    col = _mentioned_column(facts, text)
    return ("col", col) if col else ("new", None)


def _fuzzy_columns(facts: Facts, text: str) -> list[Col]:
    """Columns that share a word with the message but are not named in full ("reading" -> reading_00, ...)."""
    topic_words = {w for words in TOPICS.values() for w in words}
    words = {
        w
        for w in re.findall(r"[a-z0-9]{4,}", text)
        if w not in CHAT_WORDS and not any(t in w or w in t for t in topic_words)
    }
    return [
        c
        for c in facts.cols
        if words & {t for t in re.split(r"\W|_", c.name.lower()) if len(t) >= 4}
    ]


def _worst_columns(cat: str, facts: Facts) -> list[str]:
    """Columns worth a follow-up tap after a whole-file answer."""
    if cat == "detective":
        return [
            c
            for c, _ in sorted(facts.outlier_counts.items(), key=lambda kv: -kv[1])[:3]
        ]
    if cat == "janitor":
        return [
            c.name
            for c in sorted(facts.cols, key=lambda c: -c.missing)[:3]
            if c.missing
        ]
    if cat == "scribe":
        return ["what columns are there?", "show some rows"]
    return []


def _mentioned_columns(facts: Facts, text: str) -> list[tuple[Col, int, int]]:
    """Every column the message names, as (column, start, end) in reading order.

    Longer names are matched first and blanked out, so "temp" is not found again inside "temp_max";
    "customer age" matches customer_age and "holidays" matches holiday.
    """
    found, masked = [], text
    for c in sorted(facts.cols, key=lambda c: -len(c.name)):
        for variant in {c.name.lower(), c.name.lower().replace("_", " ")}:
            m = variant and re.search(
                rf"(?<!\w){re.escape(variant)}(?:e?s)?(?!\w)", masked
            )
            if m:
                found.append((c, m.start(), m.end()))
                masked = (
                    masked[: m.start()]
                    + " " * (m.end() - m.start())
                    + masked[m.end() :]
                )
                break
    return sorted(found, key=lambda f: f[1])


def _mentioned_column(facts: Facts, text: str) -> Col | None:
    found = _mentioned_columns(facts, text)
    return found[0][0] if found else None


def _wanted(text: str, lo: int = 0, hi: int | None = None) -> tuple[str, ...]:
    """The stats a question asks for, optionally only those named between `lo` and `hi`."""
    hi = len(text) if hi is None else hi
    return tuple(
        stat
        for stat, words in WANTED
        if any(lo <= m.start() < hi for m in words.finditer(text))
    )


def _as_list(reply: Reply | list[Reply]) -> list[Reply]:
    return reply if isinstance(reply, list) else [reply]


def _mentioned_value(
    facts: Facts, text: str, col: Col | None
) -> tuple[Col, str, int] | None:
    """A text value from the data that the message names ("Labor Day"): (column, value, count). Longest wins."""
    best = None
    for c in [col] if col else facts.cols:
        if c.kind != "text":
            continue
        for v, n in c.top:
            if (
                len(v) >= 3
                and re.search(rf"(?<!\w){re.escape(v.lower())}(?!\w)", text)
                and (best is None or len(v) > len(best[1]))
            ):
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
    more = (
        f"\n...and {col.distinct - len(shown):,} more."
        if col.distinct > len(shown)
        else ""
    )
    gap = f"\n({col.missing:,} cells are missing.)" if col.missing else ""
    return f"{head}\n{body}{more}{gap}"


def _columns_text(facts: Facts) -> str:
    shown = [f"{c.name} ({c.kind})" for c in facts.cols[:40]]
    more = f", ...and {len(facts.cols) - 40} more" if len(facts.cols) > 40 else ""
    return f"{len(facts.cols)} columns: {', '.join(shown)}{more}."


def _sample_text(facts: Facts) -> str:
    cols = facts.cols[:8]
    rows = [
        f"row {i}: " + ", ".join(f"{c.name}={r[j] or '-'}" for j, c in enumerate(cols))
        for i, r in enumerate(facts.head, 1)
    ]
    note = (
        f" (first {len(cols)} of {len(facts.cols)} columns)"
        if len(facts.cols) > len(cols)
        else ""
    )
    return f"the first {len(rows)} rows{note}:\n" + "\n".join(rows)


def answer(
    cat: str,
    facts: Facts,
    col: Col | None,
    cards: list[dict],
    more: bool = False,
    wanted: tuple[str, ...] = (),
) -> str:
    """A cat's chat answer, from the facts (about one column) or its own cards."""
    if col and cat == "detective":
        if col.kind != "number":
            return f"{col.name} is not a number column, so no outliers to chase. It has {col.distinct:,} distinct values."
        if col.name in facts.flat:
            return (f"at least half of {col.name} is {_fmt(col.stats['q1'])}, so the usual-range rule can't judge it: "
                    "every other value would look extreme. its histogram shows how the rest spread out.")
        n = facts.outlier_counts.get(col.name, 0)
        s = col.stats
        text = (
            (
                f"{col.name} has {n:,} values outside the usual range "
                f"(more than 1.5x the IQR beyond {_fmt(s['q1'])} to {_fmt(s['q3'])})."
            )
            if n
            else f"{col.name} looks clean: no values far outside {_fmt(s['q1'])} to {_fmt(s['q3'])}."
        )
        if col.strays:
            text += f" It also has non-numbers like {', '.join(repr(v) for v in col.strays)}."
        rows = [e for e in facts.outlier_examples if e[1] == col.name][:3]
        if more and rows:
            text += (
                " Most extreme: "
                + "; ".join(f"row {r[0]} = {_fmt(r[2])}" for r in rows)
                + "."
            )
        return text
    if col and cat == "janitor":
        pct = col.missing / max(1, facts.rows) * 100
        return f"{col.name} has {col.missing:,} missing values ({pct:.1f}%). I would {_missing_action(col, pct)}."
    if col:
        return (
            _stat_text(col, wanted, facts.rows)
            if wanted
            else _profile_text(col, facts.rows)
        )
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
        return (
            f"{col.name} is a number column: min {_fmt(s['min'])}, median {_fmt(s['median'])}, "
            f"mean {_fmt(s['mean'])}, max {_fmt(s['max'])}; {missing}."
        )
    if col.kind == "date" and s:
        return (
            f"{col.name} is a date column from {s['first']} to {s['last']}; {missing}."
        )
    common = ", ".join(f"{v!r} ({n:,})" for v, n in col.top[:3]) or "none"
    return f"{col.name} is text with {col.distinct:,} distinct values; most common: {common}; {missing}."


def _stat_text(col: Col, wanted: tuple[str, ...], rows: int) -> str:
    """Only the numbers the question asked for ("the highest temp is 310.07")."""
    s, name, said = col.stats, col.name, []
    for w in wanted:
        if w in ("mode", "rare") and col.top:
            value, n = col.top[0] if w == "mode" else col.top[-1]
            sure = w == "mode" or col.distinct <= len(
                col.top
            )  # top holds only the most common values
            said.append(
                f"the {'most' if w == 'mode' else 'least'} common {name} is {value!r} ({n:,} rows)"
                + ("" if sure else f", among its {len(col.top)} most common values")
            )
        elif col.kind == "number" and s:
            said.append(
                {
                    "min": f"the lowest {name} is {_fmt(s['min'])}",
                    "max": f"the highest {name} is {_fmt(s['max'])}",
                    "range": f"{name} goes from {_fmt(s['min'])} to {_fmt(s['max'])}",
                    "mean": f"the mean {name} is {_fmt(s['mean'])}",
                    "median": f"the median {name} is {_fmt(s['median'])}",
                    "std": f"the standard deviation of {name} is {_fmt(s['std'])}",
                    "quartiles": f"the middle half of {name} is between {_fmt(s['q1'])} and {_fmt(s['q3'])}",
                    "sum": f"{name} adds up to {_fmt(s['sum'])}",
                }[w]
            )
        elif col.kind == "date" and s and w in ("min", "max", "range"):
            said.append(
                {
                    "min": f"the earliest {name} is {s['first']}",
                    "max": f"the latest {name} is {s['last']}",
                    "range": f"{name} runs from {s['first']} to {s['last']}",
                }[w]
            )
    if not said:  # e.g. the highest of a text column
        return (
            f"{name} is not a number column, so it has no {STAT_LABEL[wanted[0]]}. "
            + _profile_text(col, rows)
        )
    text = "; ".join(said)
    return text[0].upper() + text[1:] + "."


def _missing_action(col: Col, pct: float) -> str:
    if pct > 40:
        return "drop column"
    return "fill with median" if col.kind == "number" else "fill with 'unknown'"


# ---------------------------------------------------------------- analysis


def _read(
    info: FileInfo, sel: Selection, keep: list[int]
) -> tuple[list[list[str]], list[int], int]:
    """The rows the user kept (only the `keep` columns), each row's data row number, and how many were excluded."""
    rows: list[list[str]] = []
    excluded_rows = 0
    rules = [(j, _matcher(value)) for j, value in sel.exclude]
    row_ids: list[int] = []  # each kept row's data row number in the file
    # shortcut: whole file held in memory; stream it in two passes if huge uploads matter.
    for i, raw in enumerate(iter_rows(info)):
        if i == 0:
            continue  # header
        cells = [
            cell_text(raw[j]) if j < len(raw) else "" for j in range(len(info.columns))
        ]
        if any(match(cells[j]) for j, match in rules):
            excluded_rows += 1
            continue
        rows.append([cells[j] for j in keep])
        row_ids.append(i)
    return rows, row_ids, excluded_rows


def analyse(info: FileInfo, selection: Selection | None = None) -> Facts:
    """Read every row of the file (minus the user's exclusions) and work out the facts the cats report."""
    sel = selection or Selection()
    keep = sel.columns if sel.columns is not None else list(range(len(info.columns)))
    rows, row_ids, excluded_rows = _read(info, sel, keep)
    if not rows:
        raise ValueError("every row was excluded by the row filter")
    n = len(rows)
    width = len(keep)

    cols = [_profile(info.columns[j], [r[k] for r in rows]) for k, j in enumerate(keep)]
    index = {id(c): j for j, c in enumerate(cols)}
    measures = [c for c in cols if c.is_measure]
    groups = sorted(
        (
            c
            for c in cols
            if c.kind == "text" and not _is_id(c.name) and 2 <= c.distinct <= 50
        ),
        key=lambda c: abs(c.distinct - 6),
    )
    date_col = next((c for c in cols if c.kind == "date"), None)
    target_col = cols[keep.index(sel.target)] if sel.target in keep else None
    focus = (
        target_col
        if target_col and target_col.is_measure
        else (measures[0] if measures else None)
    )

    seen: dict[tuple, int] = {}
    duplicates = []
    for i, r in enumerate(rows):
        first = seen.setdefault(tuple(r), i)
        if first != i:
            duplicates.append((row_ids[first], row_ids[i]))
    del seen

    outlier_counts, examples, flagged, flat = {}, [], set(), []
    for c in measures:
        s = c.stats
        if c.distinct <= 2 or not s:
            continue  # flags and constants have no "usual range"
        if s["q1"] == s["q3"]:
            flat.append(c.name)  # half the values are one number (rain: mostly 0): the rule would flag all the rest
            continue
        iqr = s["q3"] - s["q1"]
        lo, hi = s["q1"] - 1.5 * iqr, s["q3"] + 1.5 * iqr
        hits = [
            i for i, x in enumerate(c.numbers) if x is not None and (x < lo or x > hi)
        ]
        if hits:
            outlier_counts[c.name] = len(hits)
            flagged.update(hits)
            for i in hits:
                x = c.numbers[i]
                examples.append(
                    [
                        row_ids[i],
                        c.name,
                        x,
                        round((x - s["mean"]) / s["std"], 1) if s["std"] else 0.0,
                    ]
                )
    examples.sort(key=lambda e: -abs(e[3]))

    mixed = 0
    if date_col:
        j = index[id(date_col)]
        iso = sum(1 for r in rows if ISO_DATE.match(r[j]))
        other = sum(
            1 for r in rows if r[j].lower() not in NA and not ISO_DATE.match(r[j])
        )
        mixed = other if iso and other else 0

    by_group = None
    group = (
        target_col
        if any(g is target_col for g in groups)
        else (groups[0] if groups else None)
    )
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
        top = [
            (label, sums[label] / k if focus else k, k)
            for label, k in counts.most_common(MAX_BARS)
        ]
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

    hist = (
        _histogram([x for x in focus.numbers if x is not None], HIST_BINS)
        if focus
        else None
    )
    pair, corr = _best_pair(measures)

    type_issues = [c for c in cols if c.kind == "number" and c.strays]
    missing_total = sum(c.missing for c in cols)
    rows_ = max(n, 1)
    # Each kind of problem can cost at most its cap, so one noisy check can't sink the score.
    score = (
        100
        - min(40, missing_total / (rows_ * max(1, width)) * 300)
        - min(25, len(duplicates) / rows_ * 500)
        - min(25, len(flagged) / rows_ * 200)
        - min(20, 5 * len(type_issues))
    )

    box = boxplot_card(focus) if focus else None
    for c in cols:
        c.numbers = []  # facts are kept for chat; the raw values are not
    return Facts(
        filename=info.filename,
        rows=n,
        cols=cols,
        all_columns=len(info.columns),
        excluded=[(info.columns[j], v) for j, v in sel.exclude],
        excluded_rows=excluded_rows,
        measures=measures,
        groups=groups,
        date_col=date_col,
        target=target_col,
        focus=focus,
        missing_total=missing_total,
        duplicates=duplicates,
        outlier_counts=outlier_counts,
        outlier_examples=examples[:20],
        outlier_rows=len(flagged),
        flat=flat,
        type_issues=type_issues,
        mixed_dates=mixed,
        by_group=by_group,
        trend=trend,
        pair=pair,
        corr=corr,
        hist=hist,
        box=box,
        health_score=round(max(0, min(100, score))),
        head=[[c[:40] for c in r] for r in rows[:5]],
        encoding=info.encoding,
        deduped=info.deduped,
    )


def _profile(name: str, values: list[str]) -> Col:
    present = [v for v in values if v.lower() not in NA]
    counts = Counter(present)
    numbers = [None if v.lower() in NA else _number(v) for v in values]
    parsed = [x for x in numbers if x is not None]
    kind = "text"
    if present and len(parsed) >= 0.9 * len(present):
        kind = "number"
    elif present and sum(
        1 for v in present if ISO_DATE.match(v) or OTHER_DATE.match(v)
    ) >= 0.8 * len(present):
        kind = "date"

    stats, strays = {}, []
    if kind == "number":
        strays = [
            v
            for v, _ in Counter(
                v for v, x in zip(values, numbers) if x is None and v.lower() not in NA
            ).most_common(3)
        ]
        if len(parsed) >= 2:
            q1, median, q3 = statistics.quantiles(parsed, n=4, method="inclusive")
            stats = {
                "min": min(parsed),
                "max": max(parsed),
                "mean": statistics.fmean(parsed),
                "median": median,
                "std": statistics.stdev(parsed),
                "q1": q1,
                "q3": q3,
                "sum": sum(parsed),
            }
    elif kind == "date":
        iso = [v[:10] for v in present if ISO_DATE.match(v)]
        if iso:
            stats = {"first": min(iso), "last": max(iso)}
    return Col(
        name=name,
        kind=kind,
        missing=len(values) - len(present),
        distinct=len(counts),
        example=present[0] if present else "",
        top=counts.most_common(TOP_VALUES),
        strays=strays,
        stats=stats,
        numbers=numbers if kind == "number" else [],
    )


def _histogram(xs: list[float], bins: int) -> tuple[list[str], list[int]] | None:
    """Equal-width bins from min to max (the last one includes max), the same bins matplotlib and R draw."""
    if not xs:
        return None
    lo, hi = min(xs), max(xs)
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int((x - lo) / width))] += 1
    return [
        f"{_fmt(lo + i * width)}-{_fmt(lo + (i + 1) * width)}" for i in range(bins)
    ], counts


def _best_pair(measures: list[Col]):
    """The two measures that move together most (Pearson r on up to CORR_SAMPLE rows)."""
    cands = [c for c in measures if c.distinct > 2][:12]
    if len(cands) < 2:
        return None, []
    n = len(cands[0].numbers)
    step = max(1, n // CORR_SAMPLE)
    best, ranked = None, []
    for i, a in enumerate(cands):
        for b in cands[i + 1 :]:
            xy = [
                (x, y)
                for x, y in zip(a.numbers[::step], b.numbers[::step])
                if x is not None and y is not None
            ]
            try:
                r = statistics.correlation([x for x, _ in xy], [y for _, y in xy])
            except statistics.StatisticsError:
                continue  # too few points, or a constant column
            ranked.append((a.name, b.name, r))
            if best is None or abs(r) > abs(best[2]):
                best = (a, b, r)
    ranked.sort(key=lambda t: -abs(t[2]))
    if best is None:
        return None, []
    a, b, _ = best
    points, r, sampled = _scatter_data(a.numbers, b.numbers)
    return (a, b, r, points, sampled), ranked


def _scatter_data(xs: list[float | None], ys: list[float | None]):
    """Points to draw (at most SCATTER_POINTS) and Pearson r (on up to CORR_SAMPLE rows) for two aligned columns.

    None when r cannot be computed: fewer than two rows with both numbers, or a column that never changes.
    """
    step = max(1, len(xs) // CORR_SAMPLE)
    sample = [(x, y) for x, y in zip(xs[::step], ys[::step]) if x is not None and y is not None]
    try:
        r = statistics.correlation([x for x, _ in sample], [y for _, y in sample])
    except statistics.StatisticsError:
        return None
    xy = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    points = [[round(x, 3), round(y, 3)] for x, y in xy[:: max(1, len(xy) // SCATTER_POINTS)]]
    return points, r, step > 1


def number_choices(f: Facts) -> list[str]:
    """Columns the chart dropdowns offer: the real measures, else any number column with stats."""
    cols = [c for c in f.measures if c.stats] or [c for c in f.cols if c.kind == "number" and c.stats]
    return [c.name for c in cols]


# ---------------------------------------------------------------- redraws
# A chart card's header dropdowns (drawer.js) redraw just that card: one column is re-read, nothing re-run.


def _numeric_profile(info: FileInfo, selection: Selection, name: str, choices: list[str] | None) -> Col:
    """Read one column the card offered (after the row filter) and profile it; ValueError if it can't be charted."""
    if name not in (choices or []):
        raise ValueError(f"{name!r} is not one of this chart's columns")
    rows, _, _ = _read(info, selection, [info.columns.index(name)])
    col = _profile(name, [row[0] for row in rows])
    if col.kind != "number" or not col.stats:
        raise ValueError(f"{name} has fewer than two numbers to chart")
    return col


def redraw_distribution(info: FileInfo, selection: Selection, old: dict, column: str, bins: int) -> dict:
    choices = old.get("column_choices")
    col = _numeric_profile(info, selection, column, choices)
    hist = _histogram([x for x in col.numbers if x is not None], bins)
    return histogram_card(column, bins, hist, col.stats, choices)


def redraw_boxplot(info: FileInfo, selection: Selection, old: dict, column: str) -> dict:
    choices = old.get("column_choices")
    return boxplot_card(_numeric_profile(info, selection, column, choices), choices)


def redraw_scatter(info: FileInfo, selection: Selection, old: dict, x: str, y: str) -> dict:
    if x == y:
        raise ValueError("Choose two different columns for X and Y")
    choices = old.get("column_choices")
    a, b = (_numeric_profile(info, selection, name, choices) for name in (x, y))
    data = _scatter_data(a.numbers, b.numbers)
    if data is None:
        raise ValueError(f"{x} and {y} share too few rows with numbers, or one of them never changes")
    return scatter_card(x, y, *data, choices)


# ------------------------------------------------------------------ cards
# Every card follows the shape documented in engines/base.py.


def _loader(f: Facts) -> str:
    """`df = ...` plus the user's row filter and column choice."""
    name = f.filename.lower()
    na = f"keep_default_na=False, na_values={NA_VALUES!r}"
    enc = "" if f.encoding == "utf-8-sig" else f", encoding={q(f.encoding)}"
    read = (
        f"pd.read_excel({q(f.filename)}, {na})"
        if name.endswith(".xlsx")
        else f"pd.read_csv({q(f.filename)}{', sep=chr(9)' if name.endswith('.tsv') else ''}{enc}, {na})"
    )
    code = f"df = {read}"
    for col, value in f.excluded:
        num = _number(value)
        code += (
            f"\ndf = df[df[{q(col)}].notna()]"
            if value == ""  # blank cells are read as NaN
            else f'\ndf = df[pd.to_numeric(df[{q(col)}], errors="coerce") != {num!r}]'
            if num is not None
            else f"\ndf = df[df[{q(col)}].astype(str).str.strip() != {q(value)}]"
        )
    if len(f.cols) < f.all_columns:
        code += f"\ndf = df[[{', '.join(q(c.name) for c in f.cols)}]]"
    return code


def _r_loader(f: Facts) -> str:
    return rcode.loader(
        f.filename,
        NA_VALUES,
        f.excluded,
        [c.name for c in f.cols],
        f.all_columns,
        f.encoding,
        f.deduped,
    )


def detective_cards(f: Facts) -> list[dict]:
    rows = max(f.rows, 1)
    worst = sorted(f.outlier_counts.items(), key=lambda kv: -kv[1])[:MAX_BARS]
    num = f.focus.name if f.focus else (f.measures[0].name if f.measures else None)
    cards = [
        {
            "id": "detective-outliers",
            "title": f"{f.outlier_rows:,} suspicious rows",
            "description": (
                "Rows with at least one value far outside its column's usual range "
                "(more than 1.5x the IQR beyond the middle half). Could be typos, could be real "
                "extremes. Worth a look before modelling."
                + (
                    f" Not judged: {', '.join(f.flat)}. At least half of each holds one value (often 0), so "
                    "every other value would look extreme; look at its histogram instead."
                    if f.flat
                    else ""
                )
                if f.measures
                else "No number columns, so there is no usual range to step outside of."
            ),
            "severity": "warn" if f.outlier_rows else "ok",
            "chart": {
                "type": "hbar",
                "title": "Outliers per column",
                "x_label": "values",
                "y_label": "column",
                "labels": [c for c, _ in worst],
                "values": [k for _, k in worst],
            }
            if worst
            else None,
            "table": {
                "columns": ["row", "column", "value", "z_score"],
                "rows": f.outlier_examples,
            }
            if f.outlier_examples
            else None,
            "code": {
                "python": f"""import pandas as pd

{_loader(f)}
s = df[{q(num)}]
q1, q3 = s.quantile([0.25, 0.75])
iqr = q3 - q1
mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
print(mask.sum(), "suspicious rows")
df[mask].head()""",
                "r": rcode.outliers(_r_loader(f), num),
            }
            if num
            else None,
        }
    ]
    dupes = len(f.duplicates)
    cards.append(
        {
            "id": "detective-duplicates",
            "title": f"{dupes:,} duplicate rows",
            "description": "Rows that are exact copies of an earlier row. Usually an export glitch; "
            "they quietly inflate counts and averages.",
            "severity": "bad" if dupes > rows * 0.01 else "warn" if dupes else "ok",
            "chart": {
                "type": "bar",
                "title": "Unique vs duplicate rows",
                "x_label": "",
                "y_label": "rows",
                "labels": ["unique", "duplicate"],
                "values": [f.rows - dupes, dupes],
            },
            "table": {
                "columns": ["first_seen_row", "duplicate_row"],
                "rows": [list(d) for d in f.duplicates[:200]],
            }
            if dupes
            else None,
            "code": {
                "python": """dupes = df[df.duplicated(keep="first")]
print(len(dupes), "duplicate rows")
df = df.drop_duplicates()""",
                "r": rcode.DUPLICATES,
            },
        }
    )
    bad = f.type_issues[0].name if f.type_issues else None
    cards.append(
        {
            "id": "detective-types",
            "title": f"{len(f.type_issues)} columns with type problems",
            "description": "Columns that are mostly numbers but contain a few strays like 'N/A', '$3.50' or '?'. "
            "pandas reads the whole column as text because of them.",
            "severity": "warn" if f.type_issues else "ok",
            "chart": None,
            "table": {
                "columns": ["column", "expected", "found", "examples"],
                "rows": [
                    [c.name, "number", "text", ", ".join(c.strays)]
                    for c in f.type_issues
                ]
                or [["(none)", "", "", ""]],
            },
            "code": {
                "python": f"""bad = pd.to_numeric(df[{q(bad)}], errors="coerce").isna() & df[{q(bad)}].notna()
print(df.loc[bad, {q(bad)}].unique()[:10])
df[{q(bad)}] = pd.to_numeric(df[{q(bad)}].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")""",
                "r": rcode.types(bad),
            }
            if bad
            else None,
        }
    )
    return cards


def boxplot_card(col: Col, choices: list[str] | None = None) -> dict | None:
    """The one box-plot template: inclusive quartiles (the same as pandas and R's quantile()), whiskers at 1.5 x IQR.

    When the middle half is a single value (rain: mostly 0) the rule would mark every other value, so the
    whiskers span the whole range and no dots are drawn, and the description says why.
    """
    xs = sorted(x for x in col.numbers if x is not None)
    if len(xs) < 2 or not col.stats:
        return None
    q1, median, q3 = (col.stats[k] for k in ("q1", "median", "q3"))
    iqr = q3 - q1
    low, high = (q1 - 1.5 * iqr, q3 + 1.5 * iqr) if iqr else (xs[0], xs[-1])
    inside = [x for x in xs if low <= x <= high]
    outliers = [x for x in xs if x < low or x > high]
    drawn = sorted(sorted(set(outliers), key=lambda x: -abs(x - median))[:BOX_OUTLIERS])
    name = col.name
    if not iqr:
        about = (f"At least half of {name} is {_fmt(q1)}, so the box is flat and the 1.5 × IQR rule would call "
                 "every other value an outlier; none are marked. The histogram shows the rest better.")
    else:
        capped = f" (the {BOX_OUTLIERS} most extreme distinct values are drawn)" if len(drawn) < len(set(outliers)) else ""
        about = f"{len(outliers):,} value(s) lie beyond the whiskers{capped}."
    card = {
        "id": "artist-boxplot",
        "title": f"Box plot of {name}",
        "description": f"Median, quartiles and whiskers at 1.5 × IQR for {name}. {about} {col.missing:,} missing.",
        "chart": {
            "type": "box",
            "title": f"Box plot of {name}",
            "x_label": name,
            "min": inside[0],
            "q1": q1,
            "median": median,
            "q3": q3,
            "max": inside[-1],
            "outliers": drawn,
        },
        "table": {
            "columns": ["statistic", "value"],
            "rows": [
                ["lower whisker", inside[0]],
                ["Q1", q1],
                ["median", median],
                ["Q3", q3],
                ["upper whisker", inside[-1]],
                ["outlier count", len(outliers)],
            ],
        },
        "code": {
            "python": f"""import matplotlib.pyplot as plt

x = pd.to_numeric(df[{q(name)}], errors="coerce").dropna()   # stray text like "N/A" becomes NaN
q1, q3 = x.quantile([0.25, 0.75])
plt.boxplot(x, whis=1.5 if q3 > q1 else (0, 100))   # a flat middle half: whiskers span everything, no dots
plt.xticks([1], [{q(name)}]); plt.title({q("Box plot of " + name)})
plt.show()""",
            "r": rcode.boxplot(name),
        },
    }
    if choices:
        card["column_choices"] = choices
    return card


def artist_cards(f: Facts) -> list[dict]:
    cards = []
    a = f.focus
    choices = number_choices(f)
    if a and f.hist:
        cards.append(histogram_card(a.name, HIST_BINS, f.hist, a.stats, choices))
    if f.box:
        cards.append({**f.box, "column_choices": choices})
    if f.by_group:
        g, top = f.by_group
        what = f"mean {a.name}" if a else "rows"
        cards.append(
            {
                "id": "artist-by-category",
                "title": f"{what} by {g.name}",
                "description": f"A bar chart, because {g.name} has {g.distinct} categories"
                f"{f' (top {MAX_BARS} shown)' if g.distinct > MAX_BARS else ''}. "
                f"Sorted so the biggest bar is easy to spot: {top[0][0]!r} leads.",
                "chart": {
                    "type": "bar",
                    "title": f"{what} by {g.name}",
                    "x_label": g.name,
                    "y_label": what,
                    "labels": [t[0] for t in top],
                    "values": [round(t[1], 2) for t in top],
                },
                "table": {
                    "columns": [g.name, what, "rows"],
                    "rows": [[t[0], round(t[1], 2), t[2]] for t in top],
                },
                "code": {
                    "python": (
                        f"""(df.groupby({q(g.name)})[{q(a.name)}].mean()
   .sort_values(ascending=False)
   .plot.bar(edgecolor="black"))
plt.show()"""
                        if a
                        else f"""df[{q(g.name)}].value_counts().plot.bar(edgecolor="black")
plt.show()"""
                    ),
                    "r": rcode.by_category(g.name, a.name if a else None),
                },
            }
        )
    if a and f.date_col and len(f.trend) >= 2:
        d = f.date_col.name
        cards.append(
            {
                "id": "artist-trend",
                "title": f"{a.name} over time",
                "description": f"A line chart of total {a.name} per month of {d}, "
                f"from {f.trend[0][0]} to {f.trend[-1][0]}"
                f"{' (last 36 months)' if len(f.trend) == 36 else ''}.",
                "chart": {
                    "type": "line",
                    "title": f"{a.name} per month",
                    "x_label": f"{d} (by month)",
                    "y_label": a.name,
                    "labels": [m for m, _ in f.trend],
                    "values": [round(v, 2) for _, v in f.trend],
                },
                "table": {
                    "columns": ["month", a.name],
                    "rows": [[m, round(v, 2)] for m, v in f.trend],
                },
                "code": {
                    "python": f"""df[{q(d)}] = pd.to_datetime(df[{q(d)}], errors="coerce")
df.set_index({q(d)})[{q(a.name)}].resample("MS").sum().plot(marker="s")
plt.show()""",
                    "r": rcode.trend(d, a.name),
                },
            }
        )
    if f.pair:
        x, y, r, points, sampled = f.pair
        cards.append(scatter_card(x.name, y.name, points, r, sampled, choices))
    correlations = _correlations_card(f)
    if correlations:
        cards.append(correlations)
    return cards


def scatter_card(x: str, y: str, points: list[list[float]], r: float, sampled: bool,
                 choices: list[str] | None = None) -> dict:
    """The one scatter template: the strongest pair first, then any pair picked in the card's header."""
    strength = "strongly" if abs(r) >= 0.7 else "moderately" if abs(r) >= 0.4 else "barely"
    card = {
        "id": "artist-scatter",
        "title": f"{x} vs {y}",
        "description": f"A scatter plot of {x} against {y}: they move {strength} "
        f"{'up together' if r >= 0 else 'opposite ways'} (r = {r:.2f}{', measured on a sample of rows' if sampled else ''}). "
        "It starts on the two number columns that move together most.",
        "chart": {"type": "scatter", "title": f"{x} vs {y}", "x_label": x, "y_label": y, "points": points},
        "table": {"columns": [x, y], "rows": points},
        "code": {
            "python": f"""df.plot.scatter(x={q(x)}, y={q(y)}, s=8)
print(df[[{q(x)}, {q(y)}]].corr())
plt.show()""",
            "r": rcode.scatter(x, y),
        },
    }
    if choices:
        card["column_choices"] = choices
    return card


def _correlations_card(f: Facts) -> dict | None:
    """Every pair of number columns: a heatmap to scan, and the pairs listed strongest first."""
    heat = _correlation_matrix(f)
    if heat is None:
        return None
    names, matrix = heat
    left_out = len(f.measures) - len(names)
    pairs = [[a, b, round(r, 3)] for a, b, r in f.corr if a in names and b in names]
    return {
        "id": "artist-correlations",
        "title": "Which number columns move together",
        "description": f"Pearson r for each pair of {len(names)} number columns: red means they rise and fall together, "
        f"blue means they move in opposite directions, pale means no straight-line link. The table lists the pairs, "
        f"strongest first. Each pair uses only the rows where both values exist"
        f"{' (on a sample of rows)' if f.pair and f.pair[4] else ''}. "
        f"{f'{left_out} other number column(s) are left out: ID-like, yes/no, constant, too few values or beyond the first {HEAT_MAX}. ' if left_out > 0 else ''}"
        "Correlation does not prove causation: a strong r is a pattern worth checking, not proof that one column "
        "causes the other.",
        "chart": {"type": "heatmap", "title": "correlation between number columns", "x_label": "", "y_label": "",
                  "labels": names, "matrix": matrix},
        "table": {"columns": ["column_a", "column_b", "r"], "rows": pairs},
        "code": {
            "python": f"""nums = df[[{", ".join(q(n) for n in names)}]].apply(pd.to_numeric, errors="coerce")
corr = nums.corr()                         # each pair uses only the rows where both values exist
print(corr.round(2))
plt.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
plt.xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
plt.yticks(range(len(corr)), corr.columns)
plt.colorbar(label="Pearson r")
plt.title("Correlation does not prove causation")
plt.tight_layout()
plt.show()""",
            "r": rcode.heatmap(names),
        },
    }


def _correlation_matrix(f: Facts) -> tuple[list[str], list[list[float | None]]] | None:
    """The pair correlations `_best_pair` already worked out, as a square matrix in file order (None: r could not be computed).

    Needs three or more columns, like the correlations card. Constant columns, columns with too few values
    and yes/no columns never reach `f.corr`, so they are left out rather than drawn as empty rows.
    """
    seen = {n for a, b, _ in f.corr for n in (a, b)}
    names = [c.name for c in f.measures if c.name in seen][:HEAT_MAX]
    if len(names) < 3:
        return None
    r = {}
    for a, b, v in f.corr:
        r[a, b] = r[b, a] = round(max(-1.0, min(1.0, v)), 3) + 0.0  # + 0.0: no "-0.0"
    return names, [[1.0 if a == b else r.get((a, b)) for b in names] for a in names]


def histogram_card(column: str, bins: int, hist: tuple[list[str], list[int]], stats: dict,
                   choices: list[str] | None = None) -> dict:
    """The one histogram template: the baseline card and every redraw from its header (column, bins) come from here."""
    labels, counts = hist
    s = stats
    skew = (
        "right-skewed: most values are modest, a few are large"
        if s and s["mean"] > s["median"] + 0.1 * s["std"]
        else "left-skewed: a long tail of small values"
        if s and s["mean"] < s["median"] - 0.1 * s["std"]
        else "fairly symmetric around the middle"
    )
    about = f" It is {skew} (median {_fmt(s['median'])}, mean {_fmt(s['mean'])})." if s else ""
    card = {
        "id": "artist-distribution",
        "title": f"Distribution of {column}",
        "description": f"A histogram with {bins} equal-width bins, because {column} is one number per row.{about}",
        "chart": {"type": "hist", "title": column, "x_label": column, "y_label": "count", "labels": labels,
                  "values": counts},
        "table": {"columns": ["bin", "count"], "rows": [[b, k] for b, k in zip(labels, counts)]},
        "code": {
            "python": f"""import matplotlib.pyplot as plt

x = pd.to_numeric(df[{q(column)}], errors="coerce")   # stray text like "N/A" becomes NaN
x.plot.hist(bins={bins}, edgecolor="black")
plt.title({q(column)}); plt.xlabel({q(column)}); plt.ylabel("count")
plt.show()""",
            "r": rcode.histogram(column, bins),
        },
        "spec": {"column": column, "bins": bins},
        "bin_choices": sorted({*BIN_CHOICES, bins}),
    }
    if choices:
        card["column_choices"] = choices  # the header dropdown's options
    return card


def scribe_cards(f: Facts) -> list[dict]:
    kinds = Counter(c.kind for c in f.cols)
    cells = max(1, f.rows * len(f.cols))
    dictionary = [[c.name, c.kind, c.example, c.missing, c.distinct] for c in f.cols]
    notes = []
    if f.outlier_rows:
        notes.append(
            f"{f.outlier_rows:,} rows have extreme values; check them before averaging."
        )
    if f.type_issues:
        notes.append(
            f"{len(f.type_issues)} number columns contain text: {', '.join(c.name for c in f.type_issues[:5])}."
        )
    worst = sorted(f.cols, key=lambda c: -c.missing)
    if worst and worst[0].missing:
        notes.append(
            f"Missing values are worst in {worst[0].name} ({worst[0].missing / max(1, f.rows):.0%} empty)."
        )
    if f.duplicates:
        notes.append(f"{len(f.duplicates):,} rows are exact duplicates.")
    if f.mixed_dates:
        notes.append(
            f"{f.mixed_dates:,} dates in {f.date_col.name} are not written as YYYY-MM-DD; parse them explicitly."
        )
    questions = []
    if f.target:
        questions.append(f"What predicts {f.target.name}?")
    if f.by_group and f.focus:
        questions.append(f"Which {f.by_group[0].name} drives {f.focus.name}?")
    if f.trend:
        questions.append(f"Is there a seasonal pattern in {f.focus.name}?")
    if f.pair:
        questions.append(
            f"Does {f.pair[0].name} explain {f.pair[1].name} (r = {f.pair[2]:.2f})?"
        )
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
                + (
                    f" You left out {f.all_columns - len(f.cols)} of {f.all_columns} columns."
                    if len(f.cols) < f.all_columns
                    else ""
                )
                + (
                    f" Your filter dropped {f.excluded_rows:,} rows."
                    if f.excluded
                    else ""
                )
            ),
            "severity": "ok",
            "chart": None,
            "table": {
                "columns": ["column", "type", "example", "missing", "distinct"],
                "rows": dictionary,
            },
        },
        {
            "id": "scribe-watch-out",
            "title": "Things to watch out for",
            "description": "\n".join(f"{i}) {n}" for i, n in enumerate(notes, 1))
            or "Nothing worrying. Suspiciously tidy.",
            "severity": "warn" if notes else "ok",
            "chart": None,
        },
        {
            "id": "scribe-next",
            "title": "Questions this data could answer",
            "description": "\n".join(f"{i}) {n}" for i, n in enumerate(questions, 1))
            or "Add a number column and ask again.",
            "chart": None,
        },
        *_number_summary(f),
        *_category_counts(f),
        *_closer_look(f),
    ]


def _number_summary(f: Facts) -> list[dict]:
    nums = [c for c in f.measures if c.stats]
    if not nums:
        return []
    keys = ("min", "q1", "median", "mean", "q3", "max", "std")
    return [
        {
            "id": "scribe-numbers",
            "title": "Number columns at a glance",
            "description": "Smallest, quartiles, middle, mean, largest and spread of every number column "
            "(ID-like columns left out). Mean far from median means a long tail.",
            "chart": None,
            "table": {
                "columns": ["column", "missing", *keys],
                "rows": [
                    [c.name, c.missing, *(round(c.stats[k], 3) for k in keys)]
                    for c in nums
                ],
            },
            "code": {
                "python": f"""nums = df[[{", ".join(q(c.name) for c in nums)}]].apply(pd.to_numeric, errors="coerce")
print(nums.describe().T.round(2))""",
                "r": rcode.number_summary([c.name for c in nums]),
            },
        }
    ]


def _category_counts(f: Facts) -> list[dict]:
    text = [c for c in f.cols if c.kind == "text" and not _is_id(c.name)]
    if not text:
        return []

    def note(c: Col) -> str:
        present = f.rows - c.missing
        return (
            "one value only: it tells rows apart by nothing"
            if c.distinct == 1
            else "almost one value per row: an ID or free text?"
            if present and c.distinct >= 0.9 * present
            else "many categories: group the rare ones"
            if c.distinct > 50
            else ""
        )

    return [
        {
            "id": "scribe-categories",
            "title": "Text columns at a glance",
            "description": "How many different values each text column has (its cardinality) and the most common ones.",
            "chart": None,
            "table": {
                "columns": ["column", "distinct", "most_common", "note"],
                "rows": [
                    [
                        c.name,
                        c.distinct,
                        ", ".join(f"{v} ({n:,})" for v, n in c.top[:3]),
                        note(c),
                    ]
                    for c in text
                ],
            },
            "code": {
                "python": f"""for col in [{", ".join(q(c.name) for c in text)}]:
    print(col, "-", df[col].nunique(), "distinct values")
    print(df[col].value_counts().head(5), end="\\n\\n")""",
                "r": rcode.category_counts([c.name for c in text]),
            },
        }
    ]


def _closer_look(f: Facts) -> list[dict]:
    """Extra analyses the baseline does not run, each suggested only because of a number shown next to it."""
    rows = max(1, f.rows)
    found: list[list[str]] = []
    for c in f.measures:
        s = c.stats
        # Pearson's median skewness, 3 * (mean - median) / std, above 0.5: a clear right tail.
        if (
            s
            and s["std"]
            and 3 * (s["mean"] - s["median"]) / s["std"] > 0.5
            and s["min"] >= 0
        ):
            found.append(
                [
                    f"{c.name}: mean {_fmt(s['mean'])} vs median {_fmt(s['median'])}",
                    f"look at {c.name} on a log scale; the long right tail squashes the histogram",
                ]
            )
    for a, b, r in f.corr:
        if abs(r) >= 0.9:
            found.append(
                [
                    f"{a} and {b}: r = {r:.2f}",
                    "check whether one is computed from the other; keep one for a model",
                ]
            )
    for c in f.cols:
        pct = c.missing / rows
        if 0.05 <= pct <= 0.4:
            found.append(
                [
                    f"{c.name}: {pct:.0%} empty",
                    (
                        f"compare rows where {c.name} is empty with the rest before filling: gaps that follow a pattern "
                        "bias the median"
                    ),
                ]
            )
    if f.target and f.target.kind == "text" and f.target.top:
        share = f.target.top[0][1] / max(1, rows - f.target.missing)
        if share >= 0.8:
            found.append(
                [
                    f"target {f.target.name}: {share:.0%} are {f.target.top[0][0]!r}",
                    "imbalanced classes: judge a model by more than accuracy",
                ]
            )
    if not found:
        return []
    return [
        {
            "id": "scribe-closer-look",
            "title": "Worth a closer look (not run)",
            "description": "Suggestions beyond the standard checks, each made only because of the evidence next to it. "
            "None of them were run; they are hypotheses to test, not findings.",
            "chart": None,
            "table": {"columns": ["evidence", "suggestion"], "rows": found[:8]},
        }
    ]


def coder_cards(f: Facts) -> list[dict]:
    cards = [
        {
            "id": "coder-load",
            "title": "Load and peek",
            "description": "Read the file and get a first look at shape, types and missing values.",
            "chart": None,
            "code": {
                "python": f"""import pandas as pd

{_loader(f)}
print(df.shape)          # ({f.rows}, {len(f.cols)})
print(df.dtypes)
print(df.isna().sum().sort_values(ascending=False).head(10))
df.head()""",
                "r": rcode.load_peek(_r_loader(f), f.rows, len(f.cols)),
            },
        }
    ]
    g = f.by_group[0].name if f.by_group else None
    num = f.focus.name if f.focus else None
    summary = 'summary = df.describe(include="number").T\nsummary["missing"] = df.isna().sum()\nprint(summary.round(2))'
    if g:
        summary += f"\n\nprint(df[{q(g)}].value_counts().head(10))"
        if num:
            summary += f'\nprint(df.groupby({q(g)})[{q(num)}].agg(["count", "mean", "median"]).round(2))'
    cards.append(
        {
            "id": "coder-summary",
            "title": "Summary statistics",
            "description": "describe() for numbers, value_counts() for the main category.",
            "chart": None,
            "code": {"python": summary, "r": rcode.summary_stats(g, num)},
        }
    )

    target = f.target or (f.measures[-1] if f.measures else None)
    if target:
        classify = target.kind != "number"
        model = (
            "LogisticRegression(max_iter=1000)" if classify else "LinearRegression()"
        )
        cards.append(
            {
                "id": "coder-baseline",
                "title": "Baseline model",
                "description": (
                    f"A quick {'classification' if classify else 'linear-regression'} baseline predicting "
                    f"{target.name}{'' if f.target else ' (no target picked, so the last number column)'}. "
                    "Not fancy, but it tells you whether a fancier model is worth the effort."
                ),
                "chart": None,
                "code": {
                    "python": f"""from sklearn.compose import make_column_transformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import {model.split('(', maxsplit=1)[0]}
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
print("{"accuracy" if classify else "R^2"}:", round(model.score(X_test, y_test), 3))""",
                    "r": rcode.baseline(target.name, classify),
                },
            }
        )
    return cards


def janitor_cards(f: Facts) -> list[dict]:
    rows = max(f.rows, 1)
    by_missing = sorted(f.cols, key=lambda c: -c.missing)
    shown = [c for c in by_missing if c.missing][:MAX_BARS]
    plan = [
        [
            c.name,
            c.missing,
            round(c.missing / rows * 100, 1),
            _missing_action(c, c.missing / rows * 100),
        ]
        for c in by_missing
        if c.missing
    ]
    text_cols = [c for c in f.cols if c.kind == "text" and not _is_id(c.name)]
    encode = [
        [
            c.name,
            c.distinct,
            "one-hot" if c.distinct <= 12 else "frequency / target encoding",
        ]
        for c in sorted(text_cols, key=lambda c: c.distinct)
    ]
    g = f.groups[0] if f.groups else text_cols[0] if text_cols else None
    deduped = f.rows - len(f.duplicates)
    fix = [c.name for c in f.type_issues]
    fix_code = "".join(
        f"""
    df[{q(c)}] = pd.to_numeric(
        df[{q(c)}].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")"""
        for c in fix
    )
    stem = f.filename.rsplit(".", 1)[0]
    return [
        {
            "id": "janitor-missing",
            "title": f"{f.missing_total:,} missing values",
            "description": "Empty cells per column, with what I would do about each. "
            "Numbers get the median (robust to outliers), text gets 'unknown', "
            "columns more than 40% empty get dropped.",
            "severity": "bad"
            if f.missing_total > rows * 0.1
            else "warn"
            if f.missing_total
            else "ok",
            "chart": {
                "type": "hbar",
                "title": "% missing per column",
                "x_label": "% missing",
                "y_label": "column",
                "labels": [c.name for c in shown],
                "values": [round(c.missing / rows * 100, 1) for c in shown],
            }
            if shown
            else None,
            "table": {
                "columns": ["column", "missing", "percent", "action"],
                "rows": plan or [["(none)", 0, 0, "nothing to do"]],
            },
            "code": {
                "python": """num_cols = df.select_dtypes("number").columns
txt_cols = df.columns.difference(num_cols)
df[num_cols] = df[num_cols].fillna(df[num_cols].median())
df[txt_cols] = df[txt_cols].fillna("unknown")""",
                "r": rcode.FILL_MISSING,
            },
        },
        {
            "id": "janitor-encoding",
            "title": "Encoding the categories",
            "description": "Text columns need to become numbers before most models will eat them. "
            "Few categories: one-hot. Lots of categories: frequency encoding.",
            "chart": {
                "type": "bar",
                "title": "distinct values per text column",
                "x_label": "column",
                "y_label": "distinct",
                "labels": [r[0] for r in encode[:MAX_BARS]],
                "values": [r[1] for r in encode[:MAX_BARS]],
            }
            if encode
            else None,
            "table": {
                "columns": ["column", "distinct_values", "strategy"],
                "rows": encode or [["(none)", 0, ""]],
            },
            "code": {
                "python": f"""df[{q(g.name)}] = df[{q(g.name)}].str.strip().str.lower()
df = pd.get_dummies(df, columns=[{q(g.name)}], prefix={q(g.name)}, dtype=int)""",
                "r": rcode.encode(g.name),
            }
            if g
            else None,
        },
        {
            "id": "janitor-recipe",
            "title": "Full cleaning recipe",
            "description": "Everything above in one function, in a safe order: dedupe, fix types, fill gaps, trim text.",
            "chart": None,
            "table": {
                "columns": ["step", "rows_before", "rows_after"],
                "rows": [
                    ["drop duplicates", f.rows, deduped],
                    ["fix types", deduped, deduped],
                    ["fill missing", deduped, deduped],
                ],
            },
            "code": {
                "python": f"""def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates().copy(){fix_code}
    num_cols = df.select_dtypes("number").columns
    txt_cols = df.columns.difference(num_cols)
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    df[txt_cols] = df[txt_cols].fillna("unknown").apply(lambda s: s.astype(str).str.strip())
    return df

df_clean = clean(df)
df_clean.to_csv({q(stem + "_clean.csv")}, index=False)""",
                "r": rcode.recipe(fix, stem + "_clean.csv"),
            },
        },
    ]


BUILDERS = {
    "detective": detective_cards,
    "artist": artist_cards,
    "scribe": scribe_cards,
    "coder": coder_cards,
    "janitor": janitor_cards,
}
