"""Conversation helpers that need no analysis facts: small talk, questions about the generated
code, and finding the card that answers a question. Pure functions over the cats' cards, so the
engine can call them without this module knowing anything about how the cards were made.
"""

from __future__ import annotations

import difflib
import random
import re

from ..cats import CAT_IDS
from . import lines

Results = dict[str, list[dict]]

# ------------------------------------------------------------ typos, "youuu"

# Words the chat rules look for, so a near miss ("avrage", "histgram") can be put right.
VOCAB = set("""average mean median minimum maximum highest lowest biggest smallest largest missing blank blanks empty
null outlier outliers duplicate duplicates histogram distribution correlation chart plot graph scatter column columns
values value rows python library libraries install explain thanks thank please summary category categories
encoding cleaning clean recipe model baseline notebook total count distinct unique sample bins title label
labels again another other change instead average standard deviation learning machine deep neural network
forecast forecasting series regression classification training testing prediction predict meaning""".split())


def normalise(text: str, known: set[str] = frozenset()) -> str:
    """Lower-case, squash stretched letters ("youuu" -> "you", "coool" -> "cool") and fix near-miss words.

    `known` holds words from the data (column-name parts, common values): a word close to one of them
    ("totl", "prices") becomes that word, and a word that already is one is left alone.
    """
    text = re.sub(r"(\w)\1{2,}\b", r"\1", text.lower())     # a stretched last letter: thanksss, youuu
    text = re.sub(r"(\w)\1{2,}", r"\1\1", text)              # stretched in the middle: coool, pleeease
    targets = sorted(VOCAB | known)

    def fix(m: re.Match) -> str:
        w = m.group(0)
        if len(w) < 4 or w in VOCAB or w in known or w in STOP:
            return w
        close = difflib.get_close_matches(w, targets, n=1, cutoff=0.88)   # 0.8 turned "learning" into "cleaning"
        return close[0] if close else w

    return re.sub(r"[a-z]+", fix, text)

# ------------------------------------------------------------- many questions

# A new question starts after "?", ";" or a new line, or at "and/also/then/plus" followed by a question word.
# "highest and lowest temp" stays one question (both stats), so a stat word alone does not split.
STARTERS = r"what|what's|whats|which|how|show|list|is|are|does|do|did|can|could|would|tell|give|any|who|why|where|when"
SPLIT_AT = re.compile(rf"\s*\?+\s*|\s*[;\n]+\s*|,?\s+(?:and|also|then|plus)\s+(?=(?:{STARTERS})\b)", re.I)


def split_questions(message: str) -> list[str]:
    """The separate questions in one message, in order."""
    parts = []
    for p in SPLIT_AT.split(message):
        p = re.sub(r"^(?:(?:and|also|then|plus)\b[\s,]*)+", "", p.strip(" ,.!"), flags=re.I)   # "? and also are..."
        p = re.sub(r"(?:[\s,]+(?:and|also|then|plus))+$", "", p, flags=re.I)
        parts.append(p)
    return [p for p in parts if len(p) > 1] or [message.strip()]


# ---------------------------------------------------------------- small talk

GREET = re.compile(r"^\s*(hi|hello|hey|hiya|yo|good (morning|afternoon|evening))\b")
THANKS = re.compile(r"\b(thanks|thank you|thx|cheers|appreciate)\b|^\s*(great|awesome|nice|cool|perfect|amazing|wow)\W*$")
BYE = re.compile(r"\b(bye|goodbye|see you|good night|cya)\b")
WHO = re.compile(r"\b(who are you|what are you|are you (an? )?(ai|bot|llm|robot|human|real|chatgpt)|which ai|"
                 r"(is|are) (this|you|the (chat|sloth|cats?)) (an? )?(ai|llm|gpt|chatgpt|powered)|"
                 r"language model|llm|chatgpt|gpt|ollama|gemma|claude|openai)\b")
HELP = re.compile(r"\b(what can you do|what can i ask|what do you do|how does this work|how do i use)\b")
REPEAT = re.compile(r"\b(repeat|say that again|say it again|explain (that|it|this) again|what did you say|come again)\b"
                    r"|^\s*(again|huh|what)\W*$")
# "Why" and "explain" questions: a language model explains them better than a card does.
WHY = re.compile(r"^\s*(why|how come)\b|\bexplain\b|\bwhat (does|do) .+ mean\b|\bwhat(?: is|'s) (a|an)\b|"
                 r"\bdifference between\b|\bshould i\b|\bwhen (should|do) i\b|\bwhy (do|did|does|is|are|would)\b")


def small_talk(text: str) -> str | None:
    """A sloth reply for greetings, thanks, goodbyes and "are you an AI?"; None for anything else."""
    short = len(text.split())
    if short <= 3 and GREET.search(text):
        return random.choice(lines.CHAT_GREET)
    if short <= 4 and THANKS.search(text):
        return random.choice(lines.CHAT_THANKS)
    if short <= 4 and BYE.search(text):
        return lines.CHAT_BYE
    if WHO.search(text):
        return lines.CHAT_WHO
    return None


# --------------------------------------------------------------- find a card

STOP = {"what", "does", "about", "that", "this", "with", "from", "have", "there", "which", "your", "could", "please",
        "tell", "show", "give", "here", "them", "they", "will", "would", "the", "and", "are", "for", "you", "how",
        "why", "can", "did", "its", "any", "use", "uses", "used", "many", "much", "rows", "row", "column", "columns",
        "data", "dataset", "code", "snippet"}
# What a chart type is called in plain words, so "what does the histogram show" finds the histogram card.
CHART_WORDS = {"hist": "histogram distribution", "bar": "bar category", "hbar": "bar", "line": "line trend time",
               "scatter": "scatter correlation relationship"}


def _stems(text: str) -> set[str]:
    """Words of a text, cut to 6 letters so "duplicates" meets "duplicated"."""
    return {w[:6] for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOP}


def find_card(results: Results, text: str, only: str | None = None, need_code: bool = False) -> tuple[str, dict] | None:
    """The (cat, card) whose title, id, chart type or description best matches the message, if any does."""
    asked = _stems(text)
    best, best_score = None, 0
    for cat in ([only] if only else CAT_IDS):
        for card in results.get(cat, []):
            if need_code and not (card.get("code") or {}).get("python"):
                continue
            chart = card.get("chart") or {}
            title = _stems(f"{card['title']} {card['id'].replace('-', ' ')} {chart.get('title', '')} "
                           f"{CHART_WORDS.get(chart.get('type'), '')}")
            score = 3 * len(asked & title) + len(asked & _stems(card.get("description", "")))
            if score > best_score:
                best, best_score = (cat, card), score
    return best if best_score >= 2 else None


# ----------------------------------------------------------- code questions

# Whole words only: "import" must not match "important", nor "code" the column "zip_code".
CODE = re.compile(r"\b(code|python|snippets?|script|execute|run (it|this|that|them|these)|seed|random_state|random (seed|state)|randomness|reproducib\w*|"
                  r"librar(y|ies)|imports?|install|pip|pandas|sklearn|scikit|matplotlib|numpy|seaborn|scipy|"
                  r"statsmodels|tensorflow|keras|torch|pytorch|plotly|notebook|ipynb|model|"
                  r"baseline|regression|classif\w*|predict\w*|train\w*|test.?size|function|rstudio|rscript|tidyverse|"
                  r"ggplot2?|in r|r (code|script|version|snippets?))\b")
WANTS_R = re.compile(r"\br\b(?!\^)|rstudio|rscript|tidyverse|ggplot")        # "r^2" is not the language
EXISTS = re.compile(r"\b(is there|are there|do you have|any|support\w*|available|also)\b")
SEED = re.compile(r"seed|random|reproducib|same (results?|split)")
LIBS = re.compile(r"librar|import|package|install|depend|pip|pandas|sklearn|scikit|matplotlib|numpy|seaborn|scipy|"
                  r"statsmodels|tensorflow|keras|torch|plotly")
SHOW = re.compile(r"\b(show|give|print|paste|see|display|write|send)\b")
SPLIT = re.compile(r"split|train|test.?size|hold.?out")
MODEL = re.compile(r"model|algorithm|regression|classif|predict|baseline|accuracy|r2|r\^2|\bfit\b")
NOTEBOOK = re.compile(r"notebook|ipynb|export|\bzip\b|download")
RUN = re.compile(r"\b(run|execute|where|path|folder|directory|load|open)\b|read_csv|read_excel|which file|what file")
EXPLAIN = re.compile(r"\b(explain|walk|what does|how does|how do|step|mean)\b")
PIP_NAMES = {"sklearn": "scikit-learn"}
MAX_CODE_LINES = 30


def imports(results: Results) -> tuple[list[str], list[str]]:
    """The modules the Python snippets import and their pip names, read from the code itself (not guessed)."""
    code = "\n".join((c.get("code") or {}).get("python") or "" for cat in CAT_IDS for c in results.get(cat, []))
    found = list(dict.fromkeys(re.findall(r"^(?:import|from)\s+(\w+)", code, re.M)))
    return found, [PIP_NAMES.get(m, m) for m in found] + (["openpyxl"] if "read_excel" in code else [])


def users_of(results: Results) -> dict[str, list[str]]:
    """Module -> titles of the snippets that import it. Snippets without imports run after "Load and peek",
    which imports pandas, so pandas is needed by every snippet."""
    found: dict[str, list[str]] = {}
    for cat in CAT_IDS:
        for card in results.get(cat, []):
            code = (card.get("code") or {}).get("python") or ""
            for module in dict.fromkeys(re.findall(r"^(?:import|from)\s+(\w+)", code, re.M)):
                found.setdefault(module, []).append(card["title"])
    return found


# Libraries people ask about by name, as they would type them -> the module name in an import.
LIB_NAMES = {"pandas": "pandas", "matplotlib": "matplotlib", "sklearn": "sklearn", "scikit": "sklearn",
             "numpy": "numpy", "seaborn": "seaborn", "scipy": "scipy", "statsmodels": "statsmodels",
             "tensorflow": "tensorflow", "keras": "keras", "torch": "torch", "pytorch": "torch", "xgboost": "xgboost",
             "plotly": "plotly", "openpyxl": "openpyxl"}
NAMED_LIB = re.compile(r"\b(" + "|".join(LIB_NAMES) + r")\b")


def code_answer(results: Results, text: str) -> tuple[str, str, list[str], dict | None]:
    """Answer a question about the generated code from the cards' own code: (cat, text, choices, code).

    Answers are about the Python snippets, or the R ones when the question says R. `code` is a
    {"python", "r", "lang"} set shown in a code box; short bits of code go inline in `backticks`.
    Follow-up suggestions are only offered when the question was too vague to answer.
    """
    snippets = [(cat, c) for cat in CAT_IDS for c in results.get(cat, []) if (c.get("code") or {}).get("python")]
    if not snippets:
        return "coder", "nothing to run yet: no snippets were written for this file.", [], None
    r = bool(WANTS_R.search(text))
    code = "\n".join(c["code"]["python"] for _, c in snippets)
    r_code = "\n".join(c["code"].get("r") or "" for _, c in snippets)
    baseline = next((c for _, c in snippets if c["id"] == "coder-baseline"), None)
    seed = (re.findall(r"set\.seed\((\d+)\)" if r else r"random_state=(\d+)", r_code if r else code) or [None])[0]
    show = lambda card: {**card["code"], "lang": "r" if r and card["code"].get("r") else "python"}

    if SEED.search(text):
        if seed:
            how = f"`set.seed({seed})` before" if r else "`random_state=" + seed + "` in"
            return "coder", (f"the only random step is the train/test split in the baseline model: {how} the split, "
                             "so it splits the same way every run. nothing else is random."), [], None
        return "coder", ("none of the snippets use randomness, so there is no seed to set. the baseline model only "
                         "appears when the data has a number column to predict."), [], None
    if LIBS.search(text):
        if r:
            return "coder", ("the R snippets use base R only, so there is nothing to install. the exceptions: `readxl` "
                             "for .xlsx files, and `nnet` (it ships with R) when the model has to pick between several "
                             "text classes."), [], None
        found, pip = imports(results)
        named = NAMED_LIB.search(text)
        if named:                              # "do i need matplotlib?": about that one library
            module = LIB_NAMES[named.group(1)]
            users = users_of(results).get(module, [])
            name = PIP_NAMES.get(module, module)
            if module == "openpyxl":
                users = ["Load and peek"] if "openpyxl" in pip else []
            if users:
                return "coder", (f"yes: {', '.join(users[:4])}{' and more' if len(users) > 4 else ''} "
                                 f"import{'s' if len(users) == 1 else ''} it. install it with `pip install {name}` "
                                 f"(or everything at once: `pip install {' '.join(pip)}`)"), [], None
            return "coder", (f"no: none of the generated snippets import {named.group(1)}, so you don't need it to run "
                             f"them. they need `pip install {' '.join(pip)}`"), [], None
        return "coder", f"the snippets import {', '.join(found)}. install them with `pip install {' '.join(pip)}`", [], None
    if r and EXISTS.search(text) and not SHOW.search(text):      # "is there R code?"
        _, card = next(((cat, c) for cat, c in snippets if c["id"] == "coder-load"), snippets[0])
        return "coder", ("yes: every snippet has an R version next to the Python one (the R tab in the code box). "
                         f"it is base R, so there is nothing to install. here is {card['title'].lower()}:"), [], show(card)
    if SHOW.search(text):
        cat, card = find_card(results, text, need_code=True) or next(
            ((cat, c) for cat, c in snippets if c["id"] == "coder-load"), snippets[0])
        return cat, f"{card['title']}:", [], show(card)
    if SPLIT.search(text) or MODEL.search(text):
        if baseline is None:
            return "coder", ("there is no model snippet: the chosen columns have no number column to predict. "
                             "pick a target (or keep a number column) and start again."), [], None
        model = (re.search(r"make_pipeline\(prep, (\w+)", code) or [None, "a model"])[1]
        size = (re.search(r"test_size=([\d.]+)", code) or [None, "0.2"])[1]
        if r:
            fit = "`nnet::multinom`" if "multinom" in r_code else "`lm`"
            if SPLIT.search(text) and not re.search(r"model|predict|baseline", text):
                return "coder", (f"it holds out {float(size):.0%} of the rows for testing and trains on the rest, "
                                 f"after `set.seed({seed})`."), [], None
            return "coder", (f"{baseline['description']} it fills gaps (median for numbers, most common value for text), "
                             f"drops columns that never change, splits {1 - float(size):.0%}/{float(size):.0%} and fits "
                             f"{fit}."), [], None
        if SPLIT.search(text) and not re.search(r"model|predict|baseline", text):
            return "coder", (f"it holds out {float(size):.0%} of the rows for testing (`test_size={size}`) and trains on "
                             f"the rest, with `random_state={seed}`."), [], None
        return "coder", (f"{baseline['description']} it fills gaps (median for numbers, most frequent for text), "
                         f"one-hot encodes the text columns, splits {1 - float(size):.0%}/{float(size):.0%} and fits "
                         f"`{model}`."), [], None
    if NOTEBOOK.search(text):
        return "coder", ("open any cat's results and use 'Export notebook (.ipynb)' or 'Download everything (.zip)' "
                         "at the bottom: every snippet is in the notebook, in order. the zip also has `analysis.R`, "
                         "all the R snippets in one script."), [], None
    if RUN.search(text):
        if r:
            read = (re.search(r"df <- ((?:read\.\w+|as\.data\.frame\(readxl::read_excel)\(\"[^\"]+\")", r_code)
                    or [None, "read.csv(...)"])[1]
            return "coder", (f"start with 'Load and peek': `df <- {read}, ...)`. keep the file in R's working folder "
                             "(`setwd(...)`), then run the snippets top to bottom, or `source(\"analysis.R\")` from the zip."), [], None
        loader = (re.search(r"df = (pd\.read_\w+\([^\n]*\))", code) or [None, "pd.read_csv(...)"])[1]
        return "coder", (f"start with 'Load and peek': `df = {loader}`. keep the file next to your script or notebook, "
                         "then run the snippets top to bottom (the notebook export has them in order)."), [], None
    if EXPLAIN.search(text):
        cat, card = find_card(results, text, need_code=True) or ("coder", baseline or snippets[0][1])
        return cat, f"{card['title']}: {card['description']}", [], None
    titles = "; ".join(c["title"] for cat, c in snippets if cat == "coder")
    return "coder", f"i wrote {len(snippets)} snippets ({titles} and more from the other cats), in Python and R. ask about them:", [
        "which libraries does the code use?", "what seed does it use?", "show the code to load the data"], None
