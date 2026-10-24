"""The engine interface. The API layer only talks to this.

`engines/local.py` is the built-in one (real statistics, stdlib only). To add
another (e.g. pandas + Ollama), implement these two methods in a new module
and return it from `engines.get_engine()`.
The frontend does not change.

Event contract (emit through `job.emit(type, **data)`), see API.md:
    delegated {cat, paper_count}
    progress  {cat, percent, message}
    result    {cat, cards: [Card, ...]}
    error     {cat, message}
    done      {health_score}

Card shape (every key except id/title/description is optional):
    {
      "id": "detective-outliers",
      "title": "...", "description": "...",
      "severity": "ok" | "warn" | "bad",
      "chart": {"type": "bar"|"hbar"|"line"|"hist"|"scatter"|"heatmap",
                "title", "x_label", "y_label",
                "labels": [...], "values": [...],      # bar / hbar / line / hist
                "points": [[x, y], ...],               # scatter
                "matrix": [[r|None, ...], ...]},       # heatmap: square, same order as labels
      "table": {"columns": [...], "rows": [[...], ...]},   # "Download data (CSV)"
      "code":  {"python": "...", "r": "..."}               # "Copy code"; r may be null
    }
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..jobs import Job


@dataclass
class Reply:
    who: str  # "sloth" or the cat id that answers
    text: str
    choices: list[str] = field(
        default_factory=list
    )  # short follow-ups the UI offers as buttons
    code: dict | None = None  # {"python": ..., "r": ...} shown in a code box
    followup: bool = False  # answers a question the cat asked, so the sloth stays quiet
    card: dict | None = (
        None  # a card the chat changed (a re-drawn chart), shown in the bubble
    )


class Engine(ABC):
    name = "base"

    @abstractmethod
    async def run(self, job: Job) -> None:
        """Do all five cats' work for `job`, emitting events. Must end with `done`."""

    @abstractmethod
    async def chat(self, job: Job | None, message: str) -> list[Reply]:
        """Answer a free-text message, one Reply per question in it. Engines should remember earlier turns."""
