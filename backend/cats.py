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


def paper_total(rows: int) -> int:
    """Papers on the sloth's table: ceil(rows / 1000), capped at 30.

    Only the animation is capped; every row is still analysed.
    """
    return min(max(1, -(-rows // ROWS_PER_PAPER)), MAX_PAPERS)


def split_papers(total: int) -> dict[str, int]:
    """Share papers between the cats so every cat gets a visible pile (at least 1)."""
    base, extra = divmod(total, len(CAT_IDS))
    return {
        cat: max(1, base + (1 if i < extra else 0)) for i, cat in enumerate(CAT_IDS)
    }
