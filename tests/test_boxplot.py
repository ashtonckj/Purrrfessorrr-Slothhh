"""Focused tests for the Python box plot recommendation."""
import unittest

from tests.test_charts import _card, _facts


class BoxPlotTest(unittest.TestCase):
    def test_quartiles_whiskers_and_outliers(self):
        card = _card(_facts(["score"], [[x] for x in [1, 2, 3, 4, 5, 100]]), "artist-boxplot")
        self.assertIsNotNone(card)
        chart = card["chart"]
        self.assertEqual(chart["type"], "box")
        self.assertEqual(chart["x_label"], "score")
        self.assertEqual(chart["outliers"], [100])
        self.assertEqual(chart["min"], 1)
        self.assertEqual(chart["max"], 5)
        self.assertEqual(chart["median"], 3.5)
        self.assertEqual(chart["q1"], 2.25)
        self.assertEqual(chart["q3"], 4.75)
        self.assertIn("plt.boxplot", card["code"]["python"])
        self.assertNotIn("r", card["code"])

    def test_missing_and_constant(self):
        card = _card(_facts(["n"], [[4], [4], [""], [4]]), "artist-boxplot")
        self.assertEqual(card["chart"]["outliers"], [])
        self.assertEqual(card["chart"]["min"], 4)
        self.assertIn("0 missing", card["description"])  # CSV inspection omits blank rows

    def test_insufficient(self):
        self.assertIsNone(_card(_facts(["n"], [[1], [""]]), "artist-boxplot"))

    def test_one_box_and_existing_histogram(self):
        facts = _facts(["a", "b"], [[i, i * 2] for i in range(1, 12)])
        from backend.engines.local import BUILDERS
        cards = BUILDERS["artist"](facts)
        self.assertEqual(sum(c["id"] == "artist-boxplot" for c in cards), 1)
        self.assertIsNotNone(_card(facts, "artist-distribution"))


if __name__ == "__main__":
    unittest.main()
