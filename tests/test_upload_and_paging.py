"""Upload cleanup and page-by-page previews."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from backend import files
from backend.files import FileInfo, inspect, preview_page


class _Upload:
    """Stands in for FastAPI's UploadFile: chunks, then optionally a stall or an error."""

    def __init__(self, chunks, then=None, filename="data.csv"):
        self.filename, self._chunks, self._then = filename, list(chunks), then

    async def read(self, size):
        if self._chunks:
            return self._chunks.pop(0)
        if self._then == "stall":
            await asyncio.sleep(30)
        if self._then == "error":
            raise OSError("connection reset")
        return b""


class UploadCleanupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(
            files, "settings", SimpleNamespace(upload_dir=self.dir, max_upload_mb=1)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def left(self):
        return sorted(p.name for p in self.dir.iterdir())

    async def test_good_upload_is_kept(self):
        info = await files.save_upload(_Upload([b"a,b\n1,2\n"]))
        self.assertEqual(self.left(), [info.path.name])

    async def test_cancelled_upload_leaves_nothing(self):
        task = asyncio.create_task(files.save_upload(_Upload([b"a,b\n" + b"1,2\n" * 100], "stall")))
        await asyncio.sleep(0.1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.left(), [])

    async def test_failed_read_leaves_nothing(self):
        with self.assertRaises(OSError):
            await files.save_upload(_Upload([b"a,b\n1,2\n"], "error"))
        self.assertEqual(self.left(), [])

    async def test_too_big_and_unreadable_files_leave_nothing(self):
        with self.assertRaises(HTTPException) as ctx:
            await files.save_upload(_Upload([b"x" * 600_000, b"x" * 600_000]))
        self.assertEqual(ctx.exception.status_code, 413)
        with self.assertRaises(HTTPException) as ctx:
            await files.save_upload(_Upload([b"a,b\n"]))  # header only
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(self.left(), [])


class PagingTest(unittest.TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / "p.csv"
        path.write_text("n,kind\n" + "".join(f"{i},{'drop' if i % 3 == 0 else 'keep'}\n" for i in range(1, 251)))
        self.info = FileInfo("paging-test", path.name, path, path.stat().st_size)
        inspect(self.info)
        self._clear()
        self.addCleanup(self._clear)

    @staticmethod
    def _clear():
        with files._pagers_lock:
            for it in files._PAGERS.values():
                it.close()
            files._PAGERS.clear()

    def pages(self, rules, show_excluded, limit):
        out, cursor = [], 0
        while True:
            page = preview_page(self.info, rules, show_excluded, cursor, limit)
            out.append(page)
            cursor = page["next"]
            if page["done"]:
                return out

    def test_resumed_pages_equal_cold_pages(self):
        for rules, show in (([], True), ([(1, "drop")], False), ([(1, "drop")], True)):
            with self.subTest(rules=rules, show=show):
                warm = self.pages(rules, show, 40)
                cold, cursor = [], 0
                while True:
                    self._clear()  # every page starts from the top of the file
                    page = preview_page(self.info, rules, show, cursor, 40)
                    cold.append(page)
                    cursor = page["next"]
                    if page["done"]:
                        break
                self.assertEqual(warm, cold)

    def test_every_row_is_seen_once(self):
        seen = [r[0] for p in self.pages([], True, 37) for r in p["rows"]]
        self.assertEqual(seen, [str(i) for i in range(1, 251)])

    def test_next_page_resumes_instead_of_rereading(self):
        first = preview_page(self.info, [], True, 0, 20)
        self.assertIn((self.info.file_id, first["next"]), files._PAGERS)
        second = preview_page(self.info, [], True, first["next"], 20)
        self.assertNotIn((self.info.file_id, first["next"]), files._PAGERS)  # taken, then parked further on
        self.assertIn((self.info.file_id, second["next"]), files._PAGERS)

    def test_a_cold_cursor_still_works_and_beyond_the_end_is_done(self):
        page = preview_page(self.info, [], True, 100, 5)
        self.assertEqual(page["rows"][0][0], "101")
        end = preview_page(self.info, [], True, 9999, 5)
        self.assertEqual((end["rows"], end["done"], end["next"]), ([], True, 250))

    def test_only_a_few_half_read_files_are_kept_open(self):
        for cursor in range(0, 12):
            preview_page(self.info, [], True, cursor * 10, 5)
        self.assertLessEqual(len(files._PAGERS), files._PAGERS_MAX)


if __name__ == "__main__":
    unittest.main()
