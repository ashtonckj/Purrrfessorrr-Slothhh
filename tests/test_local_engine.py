"""Run with: python -m unittest discover tests"""

import asyncio
import csv
import random
import tempfile
import unittest
from pathlib import Path

from backend.engines.local import BUILDERS, LocalEngine, analyse
from backend.files import FileInfo, inspect
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
