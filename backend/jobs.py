"""In-memory job registry with a replayable event log.

Engines call `job.emit(...)`; the SSE endpoint calls `job.stream(...)`.
Every event is kept, so a browser that reconnects (or connects late)
replays what it missed using the standard Last-Event-ID header.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .files import FileInfo, Selection


@dataclass
class Event:
    id: int
    type: str
    data: dict[str, Any]


@dataclass
class Job:
    id: str
    file: FileInfo
    selection: Selection = field(default_factory=Selection)
    events: list[Event] = field(default_factory=list)
    results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    health_score: int | None = None
    finished: bool = False
    _changed: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def emit(self, type_: str, **data: Any) -> None:
        """Record an event and wake every listener."""
        if type_ == "result":
            self.results[data["cat"]] = data["cards"]
        elif type_ == "done":
            self.health_score = data.get("health_score")
            self.finished = True
        async with self._changed:
            self.events.append(Event(len(self.events), type_, data))
            self._changed.notify_all()

    async def stream(
        self, start: int = 0, keepalive: float = 15.0
    ) -> AsyncIterator[Event | None]:
        """Yield events from index `start`; yields None as a keep-alive tick.

        Ends once the job is finished and everything has been sent.
        """
        index = start
        while True:
            while index < len(self.events):
                yield self.events[index]
                index += 1
            if self.finished:
                return
            idle = False
            async with self._changed:
                try:
                    await asyncio.wait_for(
                        self._changed.wait_for(
                            lambda: len(self.events) > index or self.finished
                        ),
                        timeout=keepalive,
                    )
                except asyncio.TimeoutError:  # not the builtin TimeoutError on Python 3.10 (see ruff.toml)
                    idle = True
            if idle:
                # Yield outside the lock: a slow client must not hold up `emit`.
                yield None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def create(self, file: FileInfo, selection: Selection) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], file=file, selection=selection)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def run_in_background(self, coro) -> None:
        # Keep a reference so the task is not garbage-collected mid-run.
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


jobs = JobStore()
