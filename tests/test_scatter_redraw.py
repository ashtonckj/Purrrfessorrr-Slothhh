import csv
import tempfile
import unittest
from pathlib import Path

from backend.engines.local import BUILDERS, analyse, scatter_card_for_columns
from backend.files import FileInfo, Selection, inspect


class ScatterRedrawTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "scatter.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["a", "b", "c", "label"])
            w.writerows([[i - 30, 2 * i - 60, 100 - i, "x"] for i in range(60)])
        self.info = FileInfo("test", path.name, path, path.stat().st_size)
        inspect(self.info)
        self.selection = Selection()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recommended_pair_remains_default(self):
        facts = analyse(self.info)
        card = next(c for c in BUILDERS["artist"](facts) if c["id"] == "artist-scatter")
        self.assertEqual(card["chart"]["x_label"], facts.pair[0].name)
        self.assertEqual(card["chart"]["y_label"], facts.pair[1].name)
        self.assertIn(facts.pair[0].name, card["scatter_columns"])
        self.assertIn(facts.pair[1].name, card["scatter_columns"])
        self.assertNotIn("label", card["scatter_columns"])

    def test_redraw_changes_labels_code_and_keeps_negative_points(self):
        card = scatter_card_for_columns(self.info, self.selection, "a", "c")
        self.assertEqual(card["chart"]["title"], "a vs c")
        self.assertEqual(card["table"]["columns"], ["a", "c"])
        self.assertIn('x="a"', card["code"]["python"])
        self.assertTrue(any(x < 0 for x, _ in card["chart"]["points"]))

    def test_invalid_pairs_rejected(self):
        for x, y in [("a", "a"), ("missing", "b"), ("a", "label")]:
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                scatter_card_for_columns(self.info, self.selection, x, y)

    def test_unselected_column_rejected(self):
        with self.assertRaises(ValueError):
            scatter_card_for_columns(self.info, Selection(columns=[0, 1]), "a", "c")


if __name__ == "__main__":
    unittest.main()
