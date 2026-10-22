"""Build the .zip and .ipynb exports from a job's cards.

Engine-agnostic: works from the card shape, so the real engine gets exports for free.
TODO(real engine): add rendered chart PNGs to the zip (the mock only has chart specs).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

from .cats import CAT_IDS, CATS
from .jobs import Job


def _table_csv(table: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(table.get("columns", []))
    writer.writerows(table.get("rows", []))
    return buf.getvalue()


def build_zip(job: Job) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("results.json", json.dumps({
            "file": job.file.public(),
            "health_score": job.health_score,
            "results": job.results,
        }, indent=2))
        zf.writestr("analysis.ipynb", json.dumps(build_notebook(job), indent=1))
        for cat in CAT_IDS:
            for card in job.results.get(cat, []):
                base = f"{cat}/{card['id']}"
                zf.writestr(f"{base}/README.md", f"# {card['title']}\n\n{card.get('description', '')}\n")
                if card.get("table"):
                    zf.writestr(f"{base}/data.csv", _table_csv(card["table"]))
                if card.get("chart"):
                    zf.writestr(f"{base}/chart.json", json.dumps(card["chart"], indent=2))
                code = (card.get("code") or {}).get("python")
                if code:
                    zf.writestr(f"{base}/code.py", code + "\n")
    return buf.getvalue()


def _md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.splitlines(keepends=True)}


def build_notebook(job: Job) -> dict:
    f = job.file
    cells = [_md(
        f"# Analysis of `{f.filename}`\n\n"
        f"{f.rows:,} rows x {f.cols} columns. Data health score: **{job.health_score}**/100.\n\n"
        "_Delegated by Purrfessorrr Slothhh, done by the cats._"
    )]
    for cat in CAT_IDS:
        cards = job.results.get(cat, [])
        if not cards:
            continue
        cells.append(_md(f"## {cat.title()} Cat\n\n{CATS[cat]}"))
        for card in cards:
            cells.append(_md(f"### {card['title']}\n\n{card.get('description', '')}"))
            code = (card.get("code") or {}).get("python")
            if code:
                cells.append(_code(code))
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "cells": cells,
    }
