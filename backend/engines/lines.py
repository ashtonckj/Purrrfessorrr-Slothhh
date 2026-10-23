"""Text the engine sends (progress lines, chat voices).

UI copy lives in static/copy.js; these lines travel through the event stream
and the chat endpoint.
"""

PROGRESS_LINES: dict[str, list[str]] = {
    "detective": [
        "putting on the hat...",
        "sniffing every row for clues",
        "interrogating the outliers",
        "dusting for duplicate pawprints",
        "checking alibis of the data types",
        "case almost closed",
    ],
    "artist": [
        "stretching paws, sharpening pencils",
        "choosing a purrfect palette",
        "sketching histograms",
        "squinting at a scatter plot",
        "adding the final whisker strokes",
    ],
    "scribe": [
        "adjusting glasses",
        "reading the column names out loud",
        "writing it in plain English",
        "crossing out the jargon",
        "polishing the summary",
    ],
    "coder": [
        "plugging in the headphones",
        "import pandas as pd",
        "typing very fast (mostly semicolons)",
        "deleting the semicolons",
        "testing the snippets",
    ],
    "janitor": [
        "grabbing the broom",
        "sweeping up missing values",
        "scrubbing weird encodings",
        "folding the categories neatly",
        "mopping the last corner",
    ],
}

DONE_LINES: dict[str, str] = {
    "detective": "case closed. found {outliers} suspicious rows",
    "artist": "{charts} charts, framed and hung",
    "scribe": "wrote it all down, pawsitively readable",
    "coder": "{snippets} snippets ready to copy",
    "janitor": "{missing} missing values swept up",
}

# How each cat opens a chat answer.
CHAT_VOICE: dict[str, str] = {
    "detective": "*adjusts hat* my case notes say:",
    "artist": "*waves brush* from my sketchbook:",
    "scribe": "*pushes up glasses* for the record:",
    "coder": "*cracks knuckles* in code terms:",
    "janitor": "*leans on broom* from the cleaning log:",
}

CHAT_BUSY: dict[str, str] = {
    cat: "still on it... ask me again when my progress bar is full!" for cat in DONE_LINES
}
CHAT_FAILED = "i tripped on this file, so i have no notes... sorry."

CHAT_NO_JOB: list[str] = [
    "hi... drop a csv in the chat first... then i delegate... it's my favourite part...",
    "no file yet... no work yet... perfect... but drop a csv if you must...",
]
CHAT_GREET: list[str] = [
    "oh... hi... drop a csv, or ask me about the data you already gave me...",
    "hello... i was almost asleep... ask me anything about your file...",
]
CHAT_THANKS: list[str] = [
    "you're welcome... the cats did the work... i napped...",
    "anytime... *yawns*",
]
CHAT_BYE = "bye... *closes eyes*... your results will be right here..."
CHAT_WHO = (
    "i'm a sloth... mostly... the five cats read every row with plain python on this computer and count things. "
    "there is no language model or internet behind us, so i answer from the results... "
    "ask about outliers, missing values, charts, code, columns, or what values a column has..."
)
CHAT_WHO_GEMMA = (
    "i'm a sloth... mostly... the five cats read every row with plain python on this computer and do all the counting. "
    "a small language model, {model}, runs here too (in ollama) to explain things and help read unusual questions... "
    "but every number about your data comes from the cats, and nothing leaves your computer..."
)
CHAT_GEMMA_DOWN = "(my language model is napping: {problem}. i'm answering from my rule book until it wakes up...)"
CHAT_GEMMA_GUESS = "i'm not sure i got that... did you mean: '{question}'?"
CHAT_GEMMA_UNCHECKED = "(the language model's answer quoted numbers i could not check against your data, so here is the rule book instead...)"
# Keep in step with the caps in analyse() (backend/engines/local.py).
CHAT_SCORE_HOW = (
    "the data health score is {score}/100... it starts at 100 and loses points for problems, each capped so "
    "one thing can't sink it: up to 40 for empty cells, 25 for duplicate rows, 25 for rows with extreme values "
    "and 20 for number columns hiding text..."
)
CHAT_NEVERMIND = "okay... never mind... *goes back to napping*"
CHAT_TAP = "tap a column for details."
CHAT_ASK_ONE = "did you mean {name}? say yes, or name another column."
CHAT_ASK_MANY = "which one did you mean: {names}{more}? tap one, or say all."
CHAT_ASK_STAT = "which column? i would guess {name} ({why})... say yes, or name another."
CHAT_NOT_READY = "the cats are still reading the file... ask me again in a moment..."
CHAT_HELP = (
    "mmh... i only delegate... ask the cats about outliers, duplicates, missing values, charts, "
    "correlations, code or a model... or ask what is inside: 'what columns are there?', "
    "'show some rows', 'what values does {example} have?'..."
)
CHAT_HEALTH: str = "the health score is {score}... {mood}..."
HEALTH_MOOD = {
    "happy": "nice and tidy... i approve, lazily",
    "meh": "could be worse... could be better... could be napping",
    "grumpy": "it's a mess... the janitor cat has notes",
}
