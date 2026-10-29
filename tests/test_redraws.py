"""The artist cards' header dropdowns: distribution (column, bins), box plot (column), scatter (x, y).

Each redraw goes through one function in local.py and one API route; only columns the card offered are accepted.
Run with: python -m unittest discover tests
"""

import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import api
from backend.engines.local import BUILDERS, analyse, redraw_boxplot, redraw_distribution, redraw_scatter
from backend.files import FileInfo, Selection, inspect
from backend.jobs import Job


class RedrawTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "cols.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["a", "b", "c", "label"])
            w.writerows([[i - 30, 2 * i - 60, 100 - i, "x"] for i in range(60)] + [[500, 1, 1, "x"]])
        self.info = FileInfo("test", path.name, path, path.stat().st_size)
        inspect(self.info)
        self.facts = analyse(self.info)
        self.cards = {c["id"]: c for c in BUILDERS["artist"](self.facts)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_cards_offer_number_columns_only(self):
        for card_id in ("artist-boxplot", "artist-distribution", "artist-scatter"):
            choices = self.cards[card_id]["column_choices"]
            self.assertEqual(choices, ["a", "b", "c"], card_id)

    def test_distribution_column_and_bins(self):
        old = self.cards["artist-distribution"]
        self.assertEqual(old["spec"], {"column": "a", "bins": 10})
        self.assertIn(10, old["bin_choices"])
        card = redraw_distribution(self.info, Selection(), old, "b", 30)
        self.assertEqual(card["spec"], {"column": "b", "bins": 30})
        self.assertEqual(len(card["chart"]["values"]), 30)
        self.assertEqual(sum(card["chart"]["values"]), 61)               # every number, once
        self.assertIn("bins=30", card["code"]["python"])
        self.assertIn("length.out = 31", card["code"]["r"])
        self.assertEqual(card["column_choices"], old["column_choices"])
        odd = redraw_distribution(self.info, Selection(), old, "b", 7)   # not a listed choice, still in range
        self.assertIn(7, odd["bin_choices"])                              # so the dropdown can show it

    def test_same_code_for_another_column(self):
        old = self.cards["artist-distribution"]
        a = redraw_distribution(self.info, Selection(), old, "a", 12)["code"]
        c = redraw_distribution(self.info, Selection(), old, "c", 12)["code"]
        for lang in ("python", "r"):
            self.assertEqual(a[lang].replace('"a"', '"X"'), c[lang].replace('"c"', '"X"'))

    def test_boxplot_for_another_column(self):
        card = redraw_boxplot(self.info, Selection(), self.cards["artist-boxplot"], "c")
        self.assertEqual(card["chart"]["x_label"], "c")
        self.assertIn('"c"', card["code"]["python"])
        self.assertIn('"c"', card["code"]["r"])
        self.assertEqual(card["column_choices"], ["a", "b", "c"])

    def test_scatter_redraw_matches_the_baseline_template(self):
        base = self.cards["artist-scatter"]
        same = redraw_scatter(self.info, Selection(), base, base["chart"]["x_label"], base["chart"]["y_label"])
        self.assertEqual(same, base)                 # picking the same pair changes nothing: one template
        card = redraw_scatter(self.info, Selection(), base, "a", "c")
        self.assertEqual((card["chart"]["title"], card["table"]["columns"]), ("a vs c", ["a", "c"]))
        self.assertIn('x="a"', card["code"]["python"])
        self.assertIn(".corr()", card["code"]["python"])
        self.assertIn("r = ", card["description"])
        self.assertTrue(any(x < 0 for x, _ in card["chart"]["points"]))

    def test_only_offered_columns_are_accepted(self):
        for build, args in ((redraw_distribution, ("label", 10)), (redraw_distribution, ("missing", 10)),
                            (redraw_boxplot, ("label",)), (redraw_scatter, ("a", "label")),
                            (redraw_scatter, ("a", "a"))):
            with self.subTest(build=build.__name__, args=args), self.assertRaises(ValueError):
                build(self.info, Selection(), self.cards["artist-scatter"], *args)
        with self.assertRaises(ValueError):                              # a card offering only a and b
            redraw_boxplot(self.info, Selection(columns=[0, 1]), {"column_choices": ["a", "b"]}, "c")

    def test_api_checks_bins_and_swaps_the_card(self):
        job = Job(id="j", file=self.info)
        job.results = {"artist": list(self.cards.values())}
        with mock.patch.object(api.jobs, "get", return_value=job):
            out = asyncio.run(api.redraw_distribution("j", api.DistributionIn(column="c", bins=20)))
            self.assertEqual(out["card"]["spec"], {"column": "c", "bins": 20})
            self.assertIs(job.results["artist"][0], out["card"])          # exports follow the redraw
            with self.assertRaises(api.HTTPException) as caught:
                asyncio.run(api.redraw_boxplot("j", api.ColumnIn(column="label")))
            self.assertEqual(caught.exception.status_code, 422)
        for bad in (1, 101):
            with self.assertRaises(ValueError):                           # pydantic rejects it before any work
                api.DistributionIn(column="c", bins=bad)


if __name__ == "__main__":
    unittest.main()
