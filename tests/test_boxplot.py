"""Focused tests for the Python box plot recommendation."""

import unittest

from tests.test_charts import _card, _facts


class BoxPlotTest(unittest.TestCase):
    def test_quartiles_whiskers_and_outliers(self):
        card = _card(
            _facts(["score"], [[x] for x in [1, 2, 3, 4, 5, 100]]), "artist-boxplot"
        )
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
        self.assertIn("bxp(", card["code"]["r"])  # an R version too, from the same quartiles

    def test_missing_and_constant(self):
        card = _card(_facts(["n"], [[4], [4], [""], [4]]), "artist-boxplot")
        self.assertEqual(card["chart"]["outliers"], [])
        self.assertEqual(card["chart"]["min"], 4)
        self.assertIn(
            "0 missing", card["description"]
        )  # CSV inspection omits blank rows

    def test_a_flat_middle_marks_no_outliers(self):
        rain = [[0]] * 40 + [[x / 10] for x in range(1, 12)]  # mostly dry hours, a few wet ones
        card = _card(_facts(["rain"], rain), "artist-boxplot")
        chart = card["chart"]
        self.assertEqual((chart["q1"], chart["q3"]), (0, 0))
        self.assertEqual(chart["outliers"], [])
        self.assertEqual((chart["min"], chart["max"]), (0, 1.1))  # whiskers over the whole range
        self.assertIn("box is flat", card["description"])
        self.assertIn("else (0, 100)", card["code"]["python"])
        self.assertIn("else range(x)", card["code"]["r"])

    def test_outlier_dots_are_distinct_and_capped(self):
        from backend.engines.local import BOX_OUTLIERS

        values = [[x % 10] for x in range(4000)] + [[1000 + x] for x in range(BOX_OUTLIERS + 50)] * 2
        card = _card(_facts(["n"], values), "artist-boxplot")
        drawn = card["chart"]["outliers"]
        self.assertEqual(len(drawn), BOX_OUTLIERS)  # 250 distinct outliers, each twice: 200 dots
        self.assertEqual(max(drawn), 1000 + BOX_OUTLIERS + 49)  # the most extreme are kept
        self.assertEqual(card["table"]["rows"][-1], ["outlier count", 2 * (BOX_OUTLIERS + 50)])
        self.assertIn("most extreme distinct values are drawn", card["description"])

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
