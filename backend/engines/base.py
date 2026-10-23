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
      "chart": {"type": "bar"|"hbar"|"line"|"hist"|"scatter",
                "title", "x_label", "y_label",
                "labels": [...], "values": [...],      # bar / hbar / line / hist
                "points": [[x, y], ...]},              # scatter
      "table": {"columns": [...], "rows": [[...], ...]},   # "Download data (CSV)"
      "code":  {"python": "...", "r": null}                # "Copy code"
    }
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..jobs import Job


class Engine(ABC):
    name = "base"

    @abstractmethod
    async def run(self, job: Job) -> None:
        """Do all five cats' work for `job`, emitting events. Must end with `done`."""

    @abstractmethod
    async def chat(self, job: Job | None, message: str) -> tuple[str, str]:
        """Answer a free-text message. Returns (who, text): "sloth" or the cat id best placed to answer."""
