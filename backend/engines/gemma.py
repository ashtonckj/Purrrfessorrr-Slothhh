"""Gemma engine: the local engine's analysis and chat rules, plus Gemma 3 (in a local Ollama) for language.

Who does what:
- Python computes every number. run() and analyse() are LocalEngine's, unchanged.
- The rules answer the sure things: named statistics, chart edits, questions about the generated code.
- Gemma discusses: why / explain / advice / machine-learning questions and their follow-ups, from facts
  Python computed. Sentences about the file with numbers not in those facts are removed (check_claims).
- When the rules cannot really answer, Gemma reads the message as a tool request (JSON, checked here).
  Measured on 17 paraphrases it picked the right tool 14 times with gemma3:4b and 5 times with gemma3:1b,
  so lookups say how they were read and chart changes are asked about first.
The order is in GemmaEngine's docstring. If Ollama is not running, the rules answer what they can.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import replace
from urllib.parse import urlparse

from ..cats import CAT_IDS
from ..jobs import Job
from . import lines, talk
from .base import Reply
from .local import (
    HELP_HINT,
    NO,
    TOPICS,
    YES,
    Convo,
    Facts,
    LocalEngine,
    _as_list,
    _chart_request,
    _is_id,
)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
RECHECK = 30            # seconds before trying an Ollama that just failed again
KEEP_ALIVE = "30m"      # how long Ollama keeps the model loaded after a request
UNCHECKED = "unchecked"


class OllamaError(Exception):
    """Ollama could not answer. The message is a reason the sloth can say."""


class Ollama:
    """A tiny client for Ollama's HTTP API (standard library only). Blocking: call it with asyncio.to_thread."""

    def __init__(self, url: str, model: str, timeout: float) -> None:
        host = urlparse(url).hostname
        if host not in LOCAL_HOSTS:     # the prompts carry facts about the user's data
            raise ValueError(f"OLLAMA_URL has to be on this computer (localhost), not {host!r}")
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self.problem: str | None = None
        self.failed_at = 0.0

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        request = urllib.request.Request(self.url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def check(self) -> str | None:
        """None when Ollama runs and has the model, else what is wrong, in words for the chat."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as response:
                names = {m.get("name") for m in json.load(response).get("models", [])}
        except (OSError, ValueError):
            return f"ollama is not running at {self.url} (open the Ollama app, or run `ollama serve`)"
        if self.model not in names and f"{self.model}:latest" not in names:
            return f"ollama has no {self.model} model (run `ollama pull {self.model}`)"
        return None

    def chat(self, messages: list[dict], schema: dict | None = None, max_tokens: int = 250) -> str:
        """The model's reply. `schema` makes Ollama return JSON of that shape (it is still checked by the caller)."""
        if self.problem and time.monotonic() - self.failed_at < RECHECK:
            raise OllamaError(self.problem)      # don't make every message wait for the same timeout
        body = {"model": self.model, "messages": messages, "stream": False, "keep_alive": KEEP_ALIVE,
                "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 8192}}
        if schema:
            body["format"] = schema
        try:
            reply = self._post("/api/chat", body, self.timeout)["message"]["content"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            slow = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
            # Ask Ollama what is wrong first: a dead server can look like a timeout too.
            reason = self.check() or (f"{self.model} took more than {self.timeout:g} s (the first answer after "
                                      "starting can take a minute while it loads)" if slow
                                      else f"ollama could not answer ({type(exc).__name__})")
            self.problem, self.failed_at = reason, time.monotonic()
            raise OllamaError(reason) from exc
        self.problem = None
        return reply

    def warm(self) -> None:
        """Load the model at start-up (a request with no prompt), so the first chat answer is not a long wait."""
        problem = self.check()
        if problem is None:
            try:
                self._post("/api/generate", {"model": self.model, "keep_alive": KEEP_ALIVE}, 300)
            except (OSError, ValueError) as exc:
                problem = f"could not load {self.model} ({type(exc).__name__})"
        print(f"  gemma: {problem}; the chat answers from its rule book until then" if problem
              else f"  gemma: {self.model} is loaded")


# ------------------------------------------------------------- tool requests

# What the model may ask for. Each maps to a plain question the rules answer, so numbers stay Python's.
TOOLS = ("stat", "missing", "outliers", "duplicates", "columns", "rows", "values", "histogram", "explain",
         "smalltalk", "unclear")
STATS = {"min": "lowest", "max": "highest", "mean": "average", "median": "median", "std": "standard deviation of",
         "sum": "sum of", "mode": "most common"}
MAX_ENUM = 100          # columns listed in the JSON schema; wider files get a free-text column (still checked)

ROUTE = """You turn a message into one tool request for a data-analysis app. Reply with JSON only.
Tools: stat (one number about a column: min, max, mean, median, std, sum, mode), missing (missing or blank values),
outliers (unusual or extreme values), duplicates (repeated rows), columns (list the columns), rows (show example rows),
values (the different values of a text column), histogram (show or change a histogram), explain (a general
data-science or code question), smalltalk (greetings, thanks, goodbye), unclear (anything else).
Use "" for column or stat and 0 for bins when they do not apply.
Columns: {columns}
Column discussed last: {last}"""
ROUTE_EXAMPLES = [
    ("how old is the youngest person", {"tool": "stat", "column": "{number}", "stat": "min", "bins": 0}),
    ("r there gaps in it", {"tool": "missing", "column": "{last}", "stat": "", "bins": 0}),
    ("what's a p-value", {"tool": "explain", "column": "", "stat": "", "bins": 0}),
    ("cheers mate", {"tool": "smalltalk", "column": "", "stat": "", "bins": 0}),
    ("blorp", {"tool": "unclear", "column": "", "stat": "", "bins": 0}),
]

EXPLAIN = """You are the data-science tutor inside Purrrfessorrr Slothhh, a beginner-friendly data analysis app.
Answer the user's latest message in at most 5 short sentences of plain English, with no headings or code.
- FACTS below were computed by Python from the user's file. They are the only source of numbers about this file (row
  counts, missing values, statistics, correlations, scores). If a number about the file is not in FACTS, say the app has
  not calculated it; never estimate it.
- General knowledge (what a method is, how a library works, typical trade-offs) can come from you.
- Make clear which parts are facts about this file and which are general advice or suggestions.
- No model is "best" without a target, a metric and a fair comparison: say what it depends on and how to test it.
- For data ordered in time, test on later periods than you train on (not a random split), and compare any complex
  model with a simple baseline first.
- Never claim the app trained or tested something it has not. Do not write code.
FACTS:
"""

# Questions that want reasoning, advice or a concept rather than a lookup: Gemma answers these first.
ADVICE = re.compile(r"\b(best|better|worse|recommend\w*|suitab\w*|appropriate|make sense|makes sense|worth|benefit\w*|"
                    r"advantages?|disadvantages?|pros|cons|trade-?offs?|limitations?|drawbacks?|useful|helpful|"
                    r"instead of|compared? (to|with)|versus)\b")
ML = re.compile(r"\b(lstm|rnn|gru|arima|sarima|prophet|transformers?|neural (net|network)s?|deep learning|random forest|"
                r"xgboost|gradient boost\w*|svm|knn|k-?means|time.?series|forecast\w*|overfit\w*|underfit\w*|"
                r"cross.?validation|hyperparameters?|feature engineering|rmse|mae|mape|machine learning)\b")
# "is it ok?": a follow-up too vague to answer without guessing what "it" is.
VAGUE = re.compile(r"(is|was|are) (it|that|this|they)( (ok|okay|good|fine|right|correct|bad))?|(it|that|this)"
                   r"( (ok|okay|good|fine|right))?|ok|okay|hmm+|so")
# "summary" questions: only these should get the scribe's whole-file summary card.
SUMMARY = re.compile(r"\b(summar\w*|overview|describe|what('s| is) in|about (the|this|my) (data|file|dataset))\b")


def tool_schema(columns: list[str]) -> dict:
    """The JSON shape Ollama must return. Listing the real column names stops most made-up ones at the source."""
    column = {"type": "string", "enum": ["", *columns]} if len(columns) <= MAX_ENUM else {"type": "string"}
    return {"type": "object", "required": ["tool", "column", "stat", "bins"], "properties": {
        "tool": {"type": "string", "enum": list(TOOLS)}, "column": column,
        "stat": {"type": "string", "enum": ["", *STATS]}, "bins": {"type": "integer"}}}


def parse_tool(raw: str, facts: Facts, message: str, last: str = "") -> dict | None:
    """Check a model's tool request against the active file. None when anything in it does not hold up.

    The column must be grounded in the message: part of its name is written there, or it is the last column
    talked about and the message says "it". A small model otherwise picks a column for anything at all."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("tool") not in TOOLS:
        return None
    name, stat, bins = data.get("column") or "", data.get("stat") or "", data.get("bins") or 0
    if not isinstance(name, str) or stat not in ("", *STATS) or not isinstance(bins, int) or isinstance(bins, bool):
        return None
    col = next((c for c in facts.cols if c.name.lower() == name.strip().lower()), None)
    if name and col is None:
        return None                              # a column this file does not have: reject, don't guess
    said = message.lower()
    if col and not (any(w[:4] in said for w in re.split(r"[\W_]+", col.name.lower()) if len(w) >= 3)
                    or (col.name == last and re.search(r"\b(it|its|that|this|them|those)\b", said))):
        return None
    if bins and str(bins) not in re.findall(r"\d+", message):
        bins = 0                                 # a number the user never wrote
    tool = data["tool"]
    if (tool == "stat" and not stat) or (tool == "values" and col is None):
        return None
    return {"tool": tool, "column": col, "stat": stat or None, "bins": bins or None}


def canonical(route: dict) -> str:
    """The plain question a checked tool request stands for, in words the rules understand."""
    col = route["column"].name if route["column"] else None
    tool = route["tool"]
    if tool == "stat":
        return f"what is the {STATS[route['stat']]} {col}?" if col else f"what is the {STATS[route['stat']]} value?"
    if tool == "histogram":
        of = f" of {col}" if col else ""
        bins = f" with {route['bins']} bins" if route["bins"] else ""
        return f"show the histogram{of}{bins}"
    return {
        "missing": f"missing values in {col}" if col else "which columns have missing values?",
        "outliers": f"any outliers in {col}?" if col else "any outliers?",
        "duplicates": "how many duplicate rows are there?",
        "columns": "what columns are there?",
        "rows": "show some rows",
        "values": f"what values does {col} have?",
    }[tool]


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _plain(n: str) -> str:
    n = n.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else n


# A sentence that talks about the user's file (its rows, cells, results or scores) makes a dataset claim.
FILE_WORDS = (r"\b(this|your|the) (data ?set|data|file|table|csv)\b|\b(rows?|columns?|cells?|duplicates?|missing|empty|"
              r"outliers?|correlat\w*|accuracy|score|rmse|mae|r2|r\^2|r squared)\b|\br\s*=|r²")


def check_claims(answer: str, source: str, names: list[str]) -> tuple[str, int]:
    """Keep the sentences whose numbers can be trusted; return (kept text, how many sentences were dropped).

    A sentence that is about this file (it names a column or the file, or talks about its rows, missing values,
    scores, ...) may only use numbers found in `source`, Python's facts and the question, small ones included
    ("0 missing" must be true too). General sentences ("hold out the last 20%", "LSTMs need long histories") may
    use any number.
    """
    seen = {_plain(n) for n in NUMBER.findall(source)}
    about_file = re.compile("|".join([FILE_WORDS, *(rf"(?<!\w){re.escape(n.lower())}(?!\w)" for n in names if n)]))
    kept, dropped = [], 0
    for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()):
        bad = [n for n in NUMBER.findall(sentence) if _plain(n) not in seen]
        if bad and about_file.search(sentence.lower()):
            dropped += 1
        else:
            kept.append(sentence)
    return " ".join(kept).strip(), dropped


def _tidy(text: str, limit: int = 900) -> str:
    """No markdown emphasis or headings, and cut at a sentence end when it runs long."""
    text = re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.MULTILINE).strip()
    if len(text) <= limit:
        return text
    cut = max(text.rfind(end, 0, limit) for end in (". ", "! ", "? "))
    return text[:cut + 1] if cut > 0 else text[:limit]


# ------------------------------------------------------------------ engine




class GemmaEngine(LocalEngine):
    """One question goes through these steps, first match wins:

    1. sure things the rules do best: a yes/no to "did you mean ...?", "are you an AI?", chart edits;
    2. discussion (why, explain, advice, machine-learning words): Gemma, with the file's facts and the last turns;
    3. the rules;
    4. when the rules did not really answer: a follow-up to the last discussion goes back to Gemma; anything else
       is read by Gemma as a tool request, checked, and answered (lookups), asked about (chart changes),
       discussed (real questions) or met with a clarifying question (vague ones).
    """
    name = "gemma"

    def __init__(self, speed: float, llm: Ollama) -> None:
        super().__init__(speed)
        self.llm = llm
        self._guesses: dict[str, str] = {}     # job id -> the question a cat asked "did you mean ...?" about
        self._told: set[str] = set()           # jobs already told that the model is down
        self._discussing: set[str] = set()     # jobs whose last answer came from Gemma, so follow-ups go back to it

    async def _no_file(self, message: str) -> list[Reply]:
        """General questions get an answer even before a file is uploaded."""
        text = talk.normalise(message)
        if talk.WHY.search(text) or ADVICE.search(text) or ML.search(text):
            try:
                answer = _tidy(await asyncio.to_thread(self.llm.chat, [
                    {"role": "system", "content": EXPLAIN + "No file is uploaded yet."},
                    {"role": "user", "content": message}], None, 300))
            except OllamaError:
                answer = ""
            if answer:
                return [Reply("sloth", answer)]
        return await super()._no_file(message)

    async def _answer(self, job: Job, question: str) -> Reply | list[Reply]:
        facts = self._facts.get(job.id)
        if facts is None:
            return await super()._answer(job, question)
        convo = self._convo.setdefault(job.id, Convo())
        text = self._normalise(facts, convo, question)
        bare = text.strip(" .!?")

        guess = self._guesses.pop(job.id, None)
        if guess and YES.fullmatch(bare):
            return _followup(await super()._answer(job, guess))
        if guess and NO.fullmatch(bare):
            return Reply("sloth", lines.CHAT_NEVERMIND, followup=True)
        if talk.WHO.search(text) and len(text.split()) <= 12:
            return Reply("sloth", lines.CHAT_WHO_GEMMA.format(model=self.llm.model))

        chart = _chart_request(text, question, facts, convo) is not None
        answering_a_cat = convo.pending is not None and len(text.split()) <= 3
        if not chart and not answering_a_cat and (talk.WHY.search(text) or ADVICE.search(text) or ML.search(text)):
            convo.pending = None                 # a new question, not the answer to a cat's "which column?"
            return await self._discuss(job, facts, convo, question, text)

        reply = await super()._answer(job, question)
        if not _missed(reply, text, job):
            self._discussing.discard(job.id)
            return reply
        if VAGUE.fullmatch(bare):
            return Reply("sloth", lines.CHAT_CLARIFY, list(lines.CHAT_CLARIFY_CHOICES))
        if job.id in self._discussing:           # "does it need a GPU?" right after talking about LSTMs
            return await self._discuss(job, facts, convo, question, text, convo.cat)
        return await self._interpret(job, facts, convo, question, text, reply)

    async def _discuss(self, job: Job, facts: Facts, convo: Convo, question: str, text: str,
                       cat: str | None = None) -> Reply | list[Reply]:
        """Gemma's answer from the file's facts and the last few turns. If the model is down, the rules answer
        when they can; otherwise the sloth says plainly that this question needs the model."""
        cat = cat or _cat_for(text, convo)
        facts_text = _context(job, facts, convo, cat, text)
        turns = []
        for asked, said in convo.history[-3:]:
            turns += [{"role": "user", "content": asked}, {"role": "assistant", "content": _unvoiced(said)}]
        try:
            answer = _tidy(await asyncio.to_thread(self.llm.chat, [
                {"role": "system", "content": EXPLAIN + facts_text}, *turns, {"role": "user", "content": question}],
                None, 300))
        except OllamaError as exc:
            return self._without_model(job, str(exc), await super()._answer(job, question), text)
        kept, dropped = check_claims(answer, f"{facts_text}\n{question}", [c.name for c in facts.cols] + [facts.filename])
        if not kept:
            return self._without_model(job, UNCHECKED, await super()._answer(job, question), text)
        convo.cat = cat
        self._discussing.add(job.id)
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {kept}" + (f" {lines.CHAT_GEMMA_TRIMMED}" if dropped else ""))

    async def _interpret(self, job: Job, facts: Facts, convo: Convo, question: str, text: str,
                         missed: Reply) -> Reply | list[Reply]:
        """For a message the rules did not really answer: Gemma reads it as a tool request, which is checked first."""
        names = [c.name for c in facts.cols]
        number = next((c.name for c in facts.measures), names[0])
        last = convo.col.name if convo.col else ""
        shots = []
        for said, tool in ROUTE_EXAMPLES:
            shots += [{"role": "user", "content": said}, {"role": "assistant", "content": json.dumps(
                {**tool, "column": tool["column"].format(number=number, last=last or number)})}]
        system = ROUTE.format(columns=", ".join(f"{c.name} ({c.kind})" for c in facts.cols[:MAX_ENUM]), last=last or "none")
        try:
            raw = await asyncio.to_thread(self.llm.chat, [{"role": "system", "content": system}, *shots,
                                                          {"role": "user", "content": question}], tool_schema(names), 60)
        except OllamaError as exc:
            return self._without_model(job, str(exc), missed, text)
        route = parse_tool(raw, facts, question, last)
        words = len(text.split())
        if route is None or route["tool"] == "unclear":
            if words >= 4:                       # a real question the tools don't cover: talk it through
                return await self._discuss(job, facts, convo, question, text)
            return Reply("sloth", lines.CHAT_CLARIFY, list(lines.CHAT_CLARIFY_CHOICES))
        if route["tool"] == "smalltalk":
            return Reply("sloth", talk.small_talk(text) or random.choice(lines.CHAT_GREET))
        if route["tool"] == "explain":
            return await self._discuss(job, facts, convo, question, text)
        ask = canonical(route)
        if route["tool"] == "histogram":         # it would change a chart: ask first
            self._guesses[job.id] = ask
            return Reply("artist", f"{lines.CHAT_VOICE['artist']} {lines.CHAT_GEMMA_GUESS.format(question=ask)}",
                         ["yes", "no"])
        answers = _as_list(await super()._answer(job, ask))   # a read-only lookup: answer, and say how it was read
        if _missed(answers[0], ask, job):
            return Reply("sloth", lines.CHAT_CLARIFY, list(lines.CHAT_CLARIFY_CHOICES))
        voice = lines.CHAT_VOICE.get(answers[0].who, "")
        first = replace(answers[0], text=answers[0].text.replace(voice, f"{voice} (reading that as '{ask}')", 1))
        return [first, *answers[1:]]

    def _without_model(self, job: Job, why: str, rules: Reply | list[Reply], text: str) -> Reply | list[Reply]:
        """No usable model answer. The rules' answer if they had a real one (with a note), never an unrelated one."""
        if _missed(_as_list(rules)[0], text, job):
            problem = lines.CHAT_GEMMA_UNCHECKED_SHORT if why == UNCHECKED else why
            return Reply("sloth", lines.CHAT_NEEDS_MODEL.format(problem=problem))
        if why == UNCHECKED:
            return [Reply("sloth", lines.CHAT_GEMMA_UNCHECKED), *_as_list(rules)]
        if job.id not in self._told:
            self._told.add(job.id)
            return [Reply("sloth", lines.CHAT_GEMMA_DOWN.format(problem=why)), *_as_list(rules)]
        return rules


def _missed(reply: Reply | list[Reply], text: str, job: Job) -> bool:
    """True when the rules did not really answer: the "ask me about..." hint, or the scribe's whole-file summary
    for a question that did not ask for a summary ("what does LSTM benefit from this dataset")."""
    reply = _as_list(reply)[0]
    if reply.who == "sloth" and reply.text.startswith(HELP_HINT) and not talk.HELP.search(text):
        return True
    summary = next((c["description"] for c in job.results.get("scribe", []) if c["id"] == "scribe-summary"), None)
    return bool(reply.who == "scribe" and summary and reply.text.endswith(summary) and not SUMMARY.search(text))


def _cat_for(text: str, convo: Convo) -> str:
    """Which cat answers a discussion: whoever spoke last for "explain that again", the coder for code and models,
    a cat whose topic is named, else the scribe (plain-English explanations are its job)."""
    if talk.REPEAT.search(text) and convo.cat:
        return convo.cat
    if talk.CODE.search(text) or ML.search(text):
        return "coder"
    return next((cat for cat in ("detective", "artist", "janitor") if any(w in text for w in TOPICS[cat])), "scribe")


def _context(job: Job, facts: Facts, convo: Convo, cat: str, text: str) -> str:
    """The FACTS Gemma gets: a summary of the file, the task, the columns asked about (or all, briefly), the
    relevant cards and what the generated code imports and does. Never the rows themselves."""
    target = facts.target or (facts.measures[-1] if facts.measures else None)
    parts = [(f"File {facts.filename}: {facts.rows} rows, {len(facts.cols)} columns; {facts.missing_total} empty cells, "
             f"{len(facts.duplicates)} duplicate rows, {facts.outlier_rows} rows with potential outliers (IQR rule); "
             f"data health {facts.health_score}/100.")]
    if target:
        task = "regression (predicting a number)" if target.kind == "number" else "classification (predicting a category)"
        who = "picked by the user" if facts.target else "not picked by the user; the generated baseline uses it by default"
        parts.append(f"Target: {target.name}, {who}. Task: {task}. No model has been trained or evaluated by the app.")
    if facts.date_col and facts.date_col.stats:
        parts.append(f"Time column: {facts.date_col.name}, from {facts.date_col.stats['first']} to "
                     f"{facts.date_col.stats['last']} (whether the rows are sorted or evenly spaced was not checked).")
    named = [c for c in facts.cols if re.search(rf"(?<!\w){re.escape(c.name.lower())}(?!\w)", text)]
    for c in (named or facts.cols)[:30]:
        s = c.stats
        if _is_id(c.name):
            about = f"ID-like, {c.distinct} distinct values"
        elif c.kind == "number" and s:
            about = f"min {s['min']:g}, median {s['median']:g}, mean {s['mean']:.4g}, max {s['max']:g}"
        elif c.kind == "date" and s:
            about = f"{s['first']} to {s['last']}"
        else:
            about = f"{c.distinct} distinct values, most common " + ", ".join(f"{v!r} ({n})" for v, n in c.top[:3])
        parts.append(f"Column {c.name} ({c.kind}): {about}; {c.missing} missing.")
    parts += [f"Correlation {a} ~ {b}: r = {r:.2f}" for a, b, r in facts.corr[:3]]
    wanted = {cat: None, "scribe-watch-out": None, "scribe-closer-look": None, "coder-baseline": None}
    cards = [(c_, card) for c_ in CAT_IDS for card in job.results.get(c_, [])]
    parts.append("Result cards: " + "; ".join(card["title"] for _, card in cards))
    parts += [f"{card['title']}: {card.get('description', '')[:300]}" for c_, card in cards
              if c_ in wanted or card["id"] in wanted]
    look = next((card for _, card in cards if card["id"] == "scribe-closer-look"), None)
    if look:
        parts += [f"Suggested, not run: {suggestion} (evidence: {evidence})" for evidence, suggestion in look["table"]["rows"]]
    users = talk.users_of(job.results)
    if users:
        _found, pip = talk.imports(job.results)
        parts.append("Generated Python code imports: " + "; ".join(
            f"{m} (in {', '.join(t[:3])})" for m, t in users.items()) +
            f". Install with: pip install {' '.join(pip)}. Every snippet uses pandas' df from 'Load and peek'. "
            "The R versions use base R only.")
    baseline = next((card for _, card in cards if card["id"] == "coder-baseline"), None)
    if baseline and "train_test_split" in baseline["code"]["python"]:
        parts.append("The generated baseline splits rows at random (train_test_split, test_size=0.2, random_state=42); "
                     "for time-ordered data a time-based split would be the fairer test.")
    return "\n".join(parts)[:9000]


def _unvoiced(said: str) -> str:
    """An earlier answer without the cats' "*adjusts hat* my case notes say:" openers."""
    return re.sub(r"\*[^*]{1,40}\*[^:]{0,40}:\s*", "", said)


def _followup(reply: Reply | list[Reply]) -> list[Reply]:
    return [replace(r, followup=True) for r in _as_list(reply)]
