"""Text the MOCK backend sends (progress lines, canned chat replies).

UI copy lives in static/copy.js. This file only matters while MOCK_MODE=true;
the real engine will generate these with Gemma instead.
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

ERROR_LINES: list[str] = [
    "tripped over a ball of yarn halfway through",
    "the file sat on my keyboard. could not finish",
    "got distracted by a red dot. sorry",
]

CHAT_REPLIES: list[str] = [
    "mmh... good question... ask the cats... they love work...",
    "i read your message... most of it... the first word...",
    "okaaay... noted... in my head... which is a nap...",
    "that sounds like a job for a cat... not a sloth...",
    "hmm... let me think about it... tomorrow...",
    "yes... probably... maybe... what was the question...",
]

CHAT_NO_JOB: list[str] = [
    "hi... drop a csv in the chat first... then i delegate... it's my favourite part...",
    "no file yet... no work yet... perfect... but drop a csv if you must...",
]

CHAT_HEALTH: str = "the health score is {score}... {mood}..."
HEALTH_MOOD = {
    "happy": "nice and tidy... i approve, lazily",
    "meh": "could be worse... could be better... could be napping",
    "grumpy": "it's a mess... the janitor cat has notes",
}
