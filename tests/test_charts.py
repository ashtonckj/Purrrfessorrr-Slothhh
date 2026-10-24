"""Time-series axis and correlation heatmap cards.

Run with: python -m unittest discover tests
"""

import csv
import random
import statistics
import tempfile
import unittest
from pathlib import Path

from backend.engines.local import BUILDERS, HEAT_MAX, analyse
from backend.files import FileInfo, inspect


def _facts(header: list[str], rows: list[list]):
    path = Path(tempfile.mkdtemp()) / "t.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return analyse(info)


def _card(facts, card_id: str) -> dict | None:
    return next((c for c in BUILDERS["artist"](facts) if c["id"] == card_id), None)


class TrendAxisTest(unittest.TestCase):
    def test_x_axis_names_the_date_column_and_months_are_in_order(self):
        rng = random.Random(3)
        dates = [f"2016-{m:02d}-{d:02d}" for m in range(1, 13) for d in (3, 17)]
        rng.shuffle(dates)                                  # rows arrive out of order
        facts = _facts(["when_sold", "sales"], [[d, rng.randint(1, 50)] for d in dates])
        chart = _card(facts, "artist-trend")["chart"]
        self.assertEqual(chart["type"], "line")
        self.assertIn("when_sold", chart["x_label"])
        self.assertEqual(chart["labels"], sorted(chart["labels"]))
        self.assertEqual(chart["labels"][0], "2016-01")
        self.assertEqual(len(chart["labels"]), 12)

    def test_other_date_formats_keep_working(self):
        # Only YYYY-MM-DD cells are charted (as before); D/M/Y cells are skipped without an error.
        rows = [[f"2020-{m:02d}-05", m] for m in range(1, 7)] + [["5/7/2020", 9], ["6/8/2020", 9]]
        facts = _facts(["day", "n"], rows)
        chart = _card(facts, "artist-trend")["chart"]
        self.assertEqual(chart["labels"], [f"2020-{m:02d}" for m in range(1, 7)])
        self.assertIn("day", chart["x_label"])
        self.assertIsNone(_card(_facts(["day", "n"], [[f"{d}/1/2020", d] for d in range(1, 10)]), "artist-trend"))


class HeatmapTest(unittest.TestCase):
    def numbers(self, n=60, cols=("a", "b", "c", "d")):
        rng = random.Random(5)
        rows = []
        for _ in range(n):
            a = rng.gauss(0, 1)
            rows.append([round(a, 3), round(2 * a + rng.gauss(0, 0.3), 3), round(rng.gauss(0, 1), 3), round(-a + rng.gauss(0, 1), 3)])
        return list(cols), rows

    def test_matrix_matches_python_correlations(self):
        header, rows = self.numbers()
        card = _card(_facts(header, rows), "artist-heatmap")
        chart = card["chart"]
        self.assertEqual(chart["type"], "heatmap")
        self.assertEqual(chart["labels"], header)
        m = chart["matrix"]
        for i in range(4):
            self.assertEqual(m[i][i], 1.0)
            for j in range(4):
                self.assertEqual(m[i][j], m[j][i])
        r = statistics.correlation([row[0] for row in rows], [row[1] for row in rows])
        self.assertAlmostEqual(m[0][1], r, places=3)
        self.assertGreater(m[0][1], 0.9)
        self.assertLess(m[0][3], 0)
        self.assertTrue(all(-1 <= v <= 1 for row in m for v in row))
        self.assertIn("does not prove causation", card["description"])
        self.assertEqual(card["table"]["columns"], ["column", *header])
        self.assertIn("python", card["code"])
        self.assertIn("pairwise", card["code"]["r"])

    def test_missing_values_use_the_rows_both_columns_have(self):
        header, rows = self.numbers()
        for i in range(0, 60, 3):
            rows[i][1] = ""                                 # blanks in b
        facts = _facts(header, rows)
        m = _card(facts, "artist-heatmap")["chart"]["matrix"]
        pairs = [(row[0], row[1]) for row in rows if row[1] != ""]
        expected = statistics.correlation([x for x, _ in pairs], [y for _, y in pairs])
        self.assertAlmostEqual(m[0][1], expected, places=3)

    def test_constant_id_and_flag_columns_are_left_out(self):
        header, rows = self.numbers()
        header = header + ["const", "row_id", "flag"]
        rows = [r + [7, i, i % 2] for i, r in enumerate(rows)]
        card = _card(_facts(header, rows), "artist-heatmap")
        self.assertEqual(card["chart"]["labels"], ["a", "b", "c", "d"])
        self.assertIn("left out", card["description"])

    def test_pair_without_shared_rows_is_empty_not_a_crash(self):
        rng = random.Random(9)
        rows = []
        for i in range(40):
            x = rng.gauss(0, 1)
            rows.append([round(x, 3) if i < 20 else "", round(x, 3) if i >= 20 else "", round(x + rng.gauss(0, 1), 3)])
        card = _card(_facts(["a", "b", "c"], rows), "artist-heatmap")
        m = card["chart"]["matrix"]
        self.assertIsNone(m[0][1])
        self.assertIsNone(m[1][0])
        self.assertIsNotNone(m[0][2])
        self.assertEqual(card["table"]["rows"][0][2], "")   # empty cell in the CSV, not "None"

    def test_too_few_number_columns_gives_no_heatmap(self):
        header, rows = self.numbers(cols=("a", "b", "c", "d"))
        two = _facts(header[:2], [r[:2] for r in rows])
        self.assertIsNone(_card(two, "artist-heatmap"))
        self.assertIsNone(_card(_facts(["a"], [[r[0]] for r in rows]), "artist-heatmap"))
        self.assertIsNone(_card(_facts(["name", "a"], [["x", r[0]] for r in rows]), "artist-heatmap"))

    def test_many_columns_are_capped(self):
        rng = random.Random(1)
        header = [f"num_{i}" for i in range(40)]
        rows = [[round(rng.gauss(0, 1), 3) for _ in header] for _ in range(200)]
        chart = _card(_facts(header, rows), "artist-heatmap")["chart"]
        self.assertEqual(len(chart["labels"]), HEAT_MAX)
        self.assertEqual(len(chart["matrix"]), HEAT_MAX)
        self.assertTrue(all(len(row) == HEAT_MAX for row in chart["matrix"]))


if __name__ == "__main__":
    unittest.main()