"""Run with: python -m unittest discover tests"""

import asyncio
import csv
import random
import tempfile
import unittest
from pathlib import Path

from backend.engines.local import BUILDERS, LocalEngine, analyse
from backend.files import FileInfo, Selection, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def _file(path: Path) -> FileInfo:
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return info


class LocalEngineTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_sample_counts_every_row(self):
        path = self.dir / "cafe.csv"
        path.write_bytes(sample_csv())
        facts = analyse(_file(path))
        self.assertEqual(facts.rows, 12063)
        self.assertEqual(len(facts.duplicates), 63)
        self.assertEqual([c.name for c in facts.type_issues], ["unit_price"])
        self.assertGreater(facts.mixed_dates, 0)
        self.assertTrue(0 <= facts.health_score <= 100)

    def test_wide_file(self):
        rng = random.Random(1)
        path = self.dir / "wide.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([f"num_{i}" for i in range(150)] + [f"cat_{i}" for i in range(50)])
            for _ in range(500):
                w.writerow([round(rng.gauss(0, 1), 3) if rng.random() > 0.05 else "" for _ in range(150)]
                           + [rng.choice("abcde") for _ in range(50)])
        facts = analyse(_file(path))
        self.assertEqual(len(facts.cols), 200)
        self.assertEqual(len(facts.measures), 150)
        for build in BUILDERS.values():
            for card in build(facts):
                self.assertTrue(card["id"] and card["title"])
                chart = card.get("chart") or {}
                self.assertLessEqual(len(chart.get("labels", [])), 10)

    def test_selection_and_row_filter(self):
        path = self.dir / "cafe.csv"
        path.write_bytes(sample_csv())
        info = _file(path)
        store, quantity, total = (info.columns.index(c) for c in ("store", "quantity", "total"))
        everything = analyse(info)
        sel = Selection(columns=[store, quantity, total], target=total, exclude=[(store, "Campus")])
        facts = analyse(info, sel)
        self.assertEqual([c.name for c in facts.cols], ["store", "quantity", "total"])
        self.assertEqual(facts.target.name, "total")
        self.assertEqual(facts.focus.name, "total")
        self.assertEqual(facts.rows + facts.excluded_rows, everything.rows)
        self.assertGreater(facts.excluded_rows, 0)
        self.assertNotIn("Campus", dict(facts.cols[0].top))
        load = BUILDERS["coder"](facts)[0]["code"]["python"]
        self.assertIn('!= "Campus"', load)
        self.assertIn('df = df[["store", "quantity", "total"]]', load)
        with self.assertRaises(ValueError):
            analyse(info, Selection(exclude=[(store, v) for v in ("Campus", "Riverside", "Old Town", "Harbour", "Station",
                                                                     "CAMPUS", "RIVERSIDE", "OLD TOWN", "HARBOUR", "STATION")]))

    def test_none_is_a_value_not_a_missing_cell(self):
        path = self.dir / "holiday.csv"
        path.write_text("holiday,temp\nNone,1\nNone,2\nLabor Day,3\nNone,\nNA,5\n")
        facts = analyse(_file(path))
        holiday, temp = facts.cols
        self.assertEqual((holiday.kind, holiday.missing, holiday.distinct), ("text", 1, 2))   # only "NA" is missing
        self.assertEqual(holiday.top[0], ("None", 3))
        self.assertEqual(temp.missing, 1)
        code = BUILDERS["coder"](facts)[0]["code"]["python"]
        self.assertIn("keep_default_na=False", code)       # pandas would otherwise turn "None" into NaN
        self.assertNotIn('"None"', code.split("na_values=")[1].split("]")[0])

    def test_exclude_treats_zero_and_zero_point_zero_alike(self):
        path = self.dir / "z.csv"
        path.write_text("n,label\n0,a\n0.0,b\n0.00,c\n1,d\n,e\n")
        info = _file(path)
        facts = analyse(info, Selection(exclude=[(0, "0")]))
        self.assertEqual((facts.rows, facts.excluded_rows), (2, 3))     # the blank cell is not zero
        facts = analyse(info, Selection(exclude=[(0, "0.0")]))
        self.assertEqual(facts.excluded_rows, 3)
        facts = analyse(info, Selection(exclude=[(1, "a")]))
        self.assertEqual(facts.excluded_rows, 1)
        self.assertIn('pd.to_numeric(df["n"], errors="coerce") != 0.0',
                      BUILDERS["coder"](analyse(info, Selection(exclude=[(0, "0")])))[0]["code"]["python"])

    def test_chat_routes_to_the_right_cat(self):
        path = self.dir / "cafe.csv"
        path.write_bytes(sample_csv())
        engine = LocalEngine(speed=0.05)
        job = Job(id="j", file=_file(path))
        asyncio.run(engine.run(job))
        ask = lambda m: asyncio.run(engine.chat(job, m))
        self.assertEqual(ask("any outliers in quantity?")[0], "detective")
        self.assertIn("missing", ask("how much is missing in rating")[1])
        self.assertEqual(ask("tell me about customer age")[0], "scribe")
        self.assertEqual(ask("show me some code")[0], "coder")
        self.assertEqual(ask("hello")[0], "sloth")


if __name__ == "__main__":
    unittest.main()
