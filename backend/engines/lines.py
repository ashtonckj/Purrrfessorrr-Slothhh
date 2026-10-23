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
