"""The five cats and their jobs. Ids here are the ids used in the API and sprites."""

CATS: dict[str, str] = {
    "detective": "Data quality: outliers, duplicates, type problems",
    "artist": "Chart selection and rendering",
    "scribe": "Plain-English explanations and documentation",
    "coder": "Python code snippets",
    "janitor": "Preprocessing and cleaning: missing values, encoding",
}

CAT_IDS: list[str] = list(CATS)

MAX_PAPERS = 30
ROWS_PER_PAPER = 1000


def paper_total(rows: int) -> tuple[int, bool]:
    """Papers on the sloth's table: ceil(rows / 1000), capped at 30.

    Returns (papers, capped).
    """
    papers = max(1, -(-rows // ROWS_PER_PAPER))
    return min(papers, MAX_PAPERS), papers > MAX_PAPERS


def split_papers(total: int) -> dict[str, int]:
    """Share papers between the cats so every cat gets a visible pile (at least 1)."""
    base, extra = divmod(total, len(CAT_IDS))
    return {
        cat: max(1, base + (1 if i < extra else 0))
        for i, cat in enumerate(CAT_IDS)
    }
