"""Header dropdowns on the artist's box plot and distribution cards."""

import csv
import tempfile
import unittest
from pathlib import Path

from backend.engines.local import (
    BUILDERS,
    analyse,
    boxplot_card_for_column,
    distribution_card_for_column,
)
from backend.files import FileInfo, Selection, inspect


class ArtistColumnsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "cols.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["a", "b", "c", "label"])
            w.writerows([[i - 30, 2 * i - 60, 100 - i, "x"] for i in range(60)] + [[500, 1, 1, "x"]])
        self.info = FileInfo("test", path.name, path, path.stat().st_size)
        inspect(self.info)
        self.selection = Selection()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cards_list_number_columns_only(self):
        cards = {c["id"]: c for c in BUILDERS["artist"](analyse(self.info))}
        for card_id in ("artist-boxplot", "artist-distribution"):
            choices = cards[card_id]["column_choices"]
            self.assertIn("a", choices)
            self.assertIn("c", choices)
            self.assertNotIn("label", choices)

    def test_boxplot_for_another_column(self):
        card = boxplot_card_for_column(self.info, self.selection, "c", ["a", "c"])
        self.assertEqual(card["id"], "artist-boxplot")
        self.assertEqual(card["chart"]["x_label"], "c")
        self.assertIn('"c"', card["code"]["python"])
        self.assertEqual(card["column_choices"], ["a", "c"])

    def test_distribution_for_another_column_keeps_bins(self):
        card = distribution_card_for_column(self.info, self.selection, "b", 5, ["a", "b"])
        self.assertEqual(card["id"], "artist-distribution")
        self.assertEqual(card["spec"]["column"], "b")
        self.assertEqual(len(card["chart"]["values"]), 5)
        self.assertEqual(card["column_choices"], ["a", "b"])

    def test_bad_columns_rejected(self):
        for build in (boxplot_card_for_column, distribution_card_for_column):
            for name in ("label", "missing"):
                with self.subTest(build=build.__name__, name=name), self.assertRaises(ValueError):
                    build(self.info, self.selection, name)
        with self.assertRaises(ValueError):
            boxplot_card_for_column(self.info, Selection(columns=[0, 1]), "c")


if __name__ == "__main__":
    unittest.main()
