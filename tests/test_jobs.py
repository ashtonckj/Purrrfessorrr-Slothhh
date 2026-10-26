"""The event stream: keep-alive ticks must not hold the job's lock."""

import asyncio
import unittest
from pathlib import Path

from backend.files import FileInfo
from backend.jobs import Job


def _job() -> Job:
    return Job(id="j", file=FileInfo("j", "a.csv", Path("a.csv"), 0))


class StreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_idle_stream_sends_keepalive_and_continues(self):
        job = _job()
        stream = job.stream(keepalive=0.01)
        self.assertIsNone(await anext(stream))  # idle: a tick, not the end of the stream
        self.assertIsNone(await anext(stream))  # ...and it keeps ticking
        await stream.aclose()

    async def test_lock_is_free_while_the_keepalive_is_yielded(self):
        job = _job()
        stream = job.stream(keepalive=0.01)
        self.assertIsNone(await anext(stream))
        # A slow consumer is parked on the tick right now; producers must not be blocked by it.
        self.assertFalse(job._changed.locked())
        await asyncio.wait_for(job.emit("progress", cat="coder", percent=5), timeout=1)
        await asyncio.wait_for(job.emit("done", health_score=90), timeout=1)
        types = [e.type async for e in stream if e is not None]
        self.assertEqual(types, ["progress", "done"])


if __name__ == "__main__":
    unittest.main()
