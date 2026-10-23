"""Run with: python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from backend.files import FileInfo, inspect, preview_page


class PreviewPageTest(unittest.TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / "holidays.csv"
        # 40 rows of "None" first, then 12 real holidays, then 8 more "None"; "0" and "0.0" mixed in col 1
        rows = ["None,0"] * 40 + [f"Holiday {i},{'0.0' if i % 2 else '5'}" for i in range(12)] + ["None,0.00"] * 8
        path.write_text("holiday,rain\n" + "\n".join(rows) + "\n")
        self.info = FileInfo("t", path.name, path, path.stat().st_size)
        inspect(self.info)

    def test_filter_reaches_rows_beyond_the_first_few(self):
        page = preview_page(self.info, [(0, "None")], show_excluded=False, cursor=0, limit=5)
        self.assertEqual([r[0] for r in page["rows"]], [f"Holiday {i}" for i in range(5)])
        self.assertFalse(page["done"])
        rest = preview_page(self.info, [(0, "None")], False, page["next"], 100)
        self.assertEqual(len(rest["rows"]), 7)
        self.assertTrue(rest["done"])

    def test_excluded_rows_are_flagged_when_shown(self):
        page = preview_page(self.info, [(0, "None")], show_excluded=True, cursor=0, limit=100)
        self.assertEqual(len(page["rows"]), 60)
        self.assertEqual(sum(page["excluded"]), 48)

    def test_zero_matches_zero_point_zero(self):
        page = preview_page(self.info, [(1, "0")], show_excluded=False, cursor=0, limit=100)
        self.assertEqual({r[1] for r in page["rows"]}, {"5"})          # every 0, 0.0 and 0.00 row is gone
        self.assertEqual(len(page["rows"]), 6)

    def test_no_rules_pages_through_everything(self):
        seen, cursor = 0, 0
        while True:
            page = preview_page(self.info, [], True, cursor, 25)
            seen += len(page["rows"])
            cursor = page["next"]
            if page["done"]:
                break
        self.assertEqual(seen, 60)


if __name__ == "__main__":
    unittest.main()
