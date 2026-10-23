"""Gemma engine: the local engine's analysis and chat rules, plus Gemma 3 (in a local Ollama) for language.

Who does what:
- Python computes every number. run() and analyse() are LocalEngine's, unchanged.
- The rules answer every question they understand: fast, tested, and they never invent a number.
- Gemma answers "why / explain / what is" questions from facts Python computed. An answer that quotes a
  number not in those facts is thrown away and the rules answer instead.
- When the rules do not understand a message, Gemma proposes a tool request (JSON, checked here) and the
  cat asks "did you mean ...?" before running it. Measured on paraphrases, gemma3:1b picks the right tool
  too rarely to act on silently.
If Ollama is not running, the rules answer alone and the sloth says once why.
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

from ..jobs import Job
from . import lines, talk
from .base import Reply
from .local import HELP_HINT, NO, TOPICS, YES, Convo, Facts, LocalEngine, _as_list

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
                "options": {"temperature": 0, "num_predict": max_tokens}}
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

EXPLAIN = """You are a patient data-science tutor inside Purrrfessorrr Slothhh, a beginner-friendly data analysis app.
Answer in 2 to 4 short sentences of plain English: no headings, lists or code blocks.
Use the facts below when the question is about the user's data, the app's results or its generated code. Python computed
them; they are the only numbers you may quote about the data. If they do not answer a question about the data, say the
app has not worked that out yet. Never invent column names or numbers. Call ideas you add suggestions, not findings.
Facts:
"""


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


def numbers_ok(answer: str, source: str) -> bool:
    """True when every number in `answer` appears in `source` (the facts and the question). Small whole numbers
    (0-10) pass, so "2 reasons" or "Python 3" are fine; a made-up mean or count is not."""
    seen = {_plain(n) for n in NUMBER.findall(source)}
    return all(_plain(n) in seen or ("." not in n and int(_plain(n)) <= 10) for n in NUMBER.findall(answer))


def _tidy(text: str) -> str:
    return re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.M).strip()[:900]


# ------------------------------------------------------------------ engine


class GemmaEngine(LocalEngine):
    name = "gemma"

    def __init__(self, speed: float, llm: Ollama) -> None:
        super().__init__(speed)
        self.llm = llm
        self._guesses: dict[str, str] = {}     # job id -> the question a cat asked "did you mean ...?" about
        self._told: set[str] = set()           # jobs already told that the model is down

    async def _no_file(self, message: str) -> list[Reply]:
        """General questions get an answer even before a file is uploaded."""
        if talk.WHY.search(talk.normalise(message)):
            try:
                answer = _tidy(await asyncio.to_thread(self.llm.chat, [
                    {"role": "system", "content": EXPLAIN + "No file is uploaded yet."},
                    {"role": "user", "content": message}]))
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
        guess = self._guesses.pop(job.id, None)
        if guess and YES.fullmatch(text.strip(" .!?")):
            return _followup(await super()._answer(job, guess))
        if guess and NO.fullmatch(text.strip(" .!?")):
            return Reply("sloth", lines.CHAT_NEVERMIND, followup=True)
        if talk.WHO.search(text) and len(text.split()) <= 12:
            return Reply("sloth", lines.CHAT_WHO_GEMMA.format(model=self.llm.model))

        if talk.WHY.search(text) and not (convo.pending and len(text.split()) <= 3):
            convo.pending = None                 # a new question, not the answer to a cat's "which column?"
            got = await self._explain(job, facts, convo, question, text)
            if isinstance(got, Reply):
                return got
            return self._with_note(job, got, await super()._answer(job, question))

        reply = await super()._answer(job, question)
        if isinstance(reply, Reply) and reply.who == "sloth" and reply.text.startswith(HELP_HINT) \
                and not talk.HELP.search(text):
            got = await self._guess(job, facts, convo, question, text)
            return got if isinstance(got, Reply) else self._with_note(job, got, reply)
        return reply

    def _with_note(self, job: Job, why: str | None, reply: Reply | list[Reply]) -> Reply | list[Reply]:
        """The rules' answer, after a note saying why the model did not answer (said once per file when it is down)."""
        if why == UNCHECKED:
            return [Reply("sloth", lines.CHAT_GEMMA_UNCHECKED), *_as_list(reply)]
        if why and job.id not in self._told:
            self._told.add(job.id)
            return [Reply("sloth", lines.CHAT_GEMMA_DOWN.format(problem=why)), *_as_list(reply)]
        return reply

    async def _explain(self, job: Job, facts: Facts, convo: Convo, question: str, text: str) -> Reply | str | None:
        """Gemma's answer from the file's facts, or why there is none (a reason, or UNCHECKED)."""
        cat = _cat_for(text, convo)
        facts_text = _context(job, facts, convo, cat)
        try:
            answer = _tidy(await asyncio.to_thread(self.llm.chat, [
                {"role": "system", "content": EXPLAIN + facts_text}, {"role": "user", "content": question}]))
        except OllamaError as exc:
            return str(exc)
        if not answer:
            return None
        if not numbers_ok(answer, f"{facts_text} {question}"):
            return UNCHECKED
        convo.cat = cat
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {answer}")

    async def _guess(self, job: Job, facts: Facts, convo: Convo, question: str, text: str) -> Reply | str | None:
        """For a message the rules did not understand: the model's checked guess, asked back as a question."""
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
            return str(exc)
        route = parse_tool(raw, facts, question, last)
        if route is None or route["tool"] == "unclear":
            return None
        if route["tool"] == "smalltalk":
            return Reply("sloth", talk.small_talk(text) or random.choice(lines.CHAT_GREET))
        if route["tool"] == "explain":
            got = await self._explain(job, facts, convo, question, text)
            return got if isinstance(got, Reply) else None
        self._guesses[job.id] = ask = canonical(route)
        cat = {"missing": "janitor", "outliers": "detective", "duplicates": "detective", "histogram": "artist"}.get(
            route["tool"], "scribe")
        return Reply(cat, f"{lines.CHAT_VOICE[cat]} {lines.CHAT_GEMMA_GUESS.format(question=ask)}", ["yes", "no"])


def _cat_for(text: str, convo: Convo) -> str:
    """Which cat explains: whoever spoke last for "explain that again", the coder for code, a cat whose topic is
    named, else the scribe (plain-English explanations are its job)."""
    if talk.REPEAT.search(text) and convo.cat:
        return convo.cat
    if talk.CODE.search(text):
        return "coder"
    return next((cat for cat in ("detective", "artist", "janitor") if any(w in text for w in TOPICS[cat])), "scribe")


def _context(job: Job, facts: Facts, convo: Convo, cat: str) -> str:
    """What the model is told: a summary of the file, the relevant cards, the code's imports, the last turns.
    Never the rows themselves."""
    parts = [f"File {facts.filename}: {facts.rows} rows, {len(facts.cols)} columns, data health {facts.health_score}/100.",
             "Columns: " + "; ".join(f"{c.name} ({c.kind}, {c.missing} missing)" for c in facts.cols[:40])]
    for c in dict.fromkeys([cat, "scribe"]):
        parts += [f"{card['title']}: {card.get('description', '')[:300]}" for card in job.results.get(c, [])[:4]]
    found, pip = talk.imports(job.results)
    if found:
        parts.append(f"The generated Python imports {', '.join(found)} (install with: pip install {' '.join(pip)}). "
                     "The R versions use base R only.")
    parts += [f"Earlier the user asked {q!r} and the app answered {a[:300]!r}" for q, a in convo.history[-2:]]
    return "\n".join(parts)


def _followup(reply: Reply | list[Reply]) -> list[Reply]:
    return [replace(r, followup=True) for r in _as_list(reply)]
