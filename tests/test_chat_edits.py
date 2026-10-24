"""Chart edits from the chat, typo-proof questions, and the baseline EDA being the same for every file.

These need no language model: they are the rules every engine shares.
Run with: python -m unittest discover tests
"""

import asyncio
import hashlib
import io
import random
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.cats import CAT_IDS
from backend.engines import talk
from backend.engines.local import BUILDERS, LocalEngine, analyse
from backend.exporters import build_zip
from backend.files import FileInfo, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def _file(path: Path) -> FileInfo:
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return info


class ChartEditTest(unittest.TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / "cafe.csv"
        path.write_bytes(sample_csv())
        self.engine = LocalEngine(speed=0.02)
        self.job = Job(id="j", file=_file(path))
        asyncio.run(self.engine.run(self.job))
        self.facts = self.engine._facts["j"]

    def ask(self, message):
        return asyncio.run(self.engine.chat(self.job, message))[0]

    def histogram(self):
        return next(c for c in self.job.results["artist"] if c["id"] == "artist-distribution")

    def test_bins_change_the_chart_and_both_codes(self):
        before = self.histogram()
        reply = self.ask("Change the histogram to 30 bins.")
        card = reply.card
        self.assertEqual((reply.who, card["spec"]["bins"]), ("artist", 30))
        self.assertEqual(len(card["chart"]["values"]), 30)
        quantity = self.facts.cols[5]
        self.assertEqual(sum(card["chart"]["values"]), self.facts.rows - quantity.missing)   # every number, once
        self.assertIn("bins=30", card["code"]["python"])
        self.assertIn("length.out = 31", card["code"]["r"])
        self.assertIs(self.histogram(), card)                       # the drawer and the exports see the new one
        self.assertIs(self.engine._facts["j"], self.facts)          # no re-analysis
        self.assertIn("bins=30", _zip_text(self.job))
        undone = self.ask("undo")
        self.assertEqual(undone.card["spec"]["bins"], 10)
        self.assertIs(self.histogram(), before)

    def test_relative_and_follow_up_edits(self):
        self.assertEqual(self.ask("can you make the histogram use more bins?").card["spec"]["bins"], 20)
        self.assertEqual(self.ask("Use 10 bins instead.").card["spec"]["bins"], 10)
        self.assertEqual(self.ask("fewer bins please").card["spec"]["bins"], 5)
        self.ask("tell me about rating")
        self.assertEqual(self.ask("show me the distribution of this column").card["spec"]["column"], "rating")

    def test_titles_keep_their_capitals(self):
        card = self.ask("Change the title to Daily Sales and the x label to Units sold").card
        self.assertEqual((card["chart"]["title"], card["chart"]["x_label"]), ("Daily Sales", "Units sold"))
        self.assertIn('plt.title("Daily Sales")', card["code"]["python"])
        self.assertIn('main = "Daily Sales"', card["code"]["r"])
        code = self.ask("Regenerate the Python code with these settings.").code
        self.assertIn('plt.title("Daily Sales")', code["python"])

    def test_same_code_for_the_same_request_on_another_column(self):
        a = self.ask("show the histogram of total with 12 bins").card["code"]
        b = self.ask("show the histogram of rating with 12 bins").card["code"]
        for lang in ("python", "r"):
            self.assertEqual(a[lang].replace('"total"', '"X"'), b[lang].replace('"rating"', '"X"'))

    def test_bad_or_vague_edits_are_explained_not_guessed(self):
        self.assertIn("between 2 and 100", self.ask("use 500 bins").text)
        self.assertIn("not numbers", self.ask("show the histogram of store").text)
        self.assertIn("i can only re-draw the histogram", self.ask("change this chart to a box plot").text)
        self.assertIn("what should they say", self.ask("can you change the chart title and axis labels?").text)
        asked = self.ask("show the distribution for another column")
        self.assertIsNone(asked.card)
        self.assertNotIn("quantity", asked.choices)                 # the one already shown
        self.assertEqual(self.ask("total").card["spec"]["column"], "total")
        self.assertIsNone(self.ask("what does the histogram show?").card)   # a question about it, not an edit

    def test_the_upload_is_never_changed(self):
        path = self.job.file.path
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        self.ask("use 40 bins")
        self.ask("show the histogram of total")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


def _zip_text(job) -> str:
    with zipfile.ZipFile(io.BytesIO(build_zip(job))) as zf:
        return "\n".join(zf.read(n).decode() for n in zf.namelist() if n.endswith((".py", ".R")))


class NormaliseTest(unittest.TestCase):
    def test_stretched_words_and_typos(self):
        known = {"total", "unit", "price", "rating"}
        self.assertEqual(talk.normalise("thank youuu", known), "thank you")
        self.assertEqual(talk.normalise("Thanksss!!", known), "thanks!!")
        self.assertEqual(talk.normalise("coool", known), "cool")
        self.assertEqual(talk.normalise("whats the avrage totl", known), "whats the average total")
        self.assertEqual(talk.normalise("weird prices", known), "weird price")
        self.assertEqual(talk.normalise("show the histgram", known), "show the histogram")
        self.assertEqual(talk.normalise("this is fine", known), "this is fine")      # real words stay
        self.assertEqual(talk.normalise("is it big enough for deep learning", known),
                         "is it big enough for deep learning")                        # not "deep cleaning"

    def test_chat_reads_them(self):
        path = Path(tempfile.mkdtemp()) / "cafe.csv"
        path.write_bytes(sample_csv())
        engine, job = LocalEngine(speed=0.02), Job(id="j", file=_file(path))
        asyncio.run(engine.run(job))
        ask = lambda m: asyncio.run(engine.chat(job, m))[0]
        self.assertEqual(ask("thank youuu").who, "sloth")
        self.assertIn("mean total", ask("whats the avrage totl").text)
        self.assertIn("unit_price", ask("can you show me the weird prices?").text)
        self.assertIn("rating has", ask("any holes in the ratings").text)
        self.assertIn("duplicate", ask("same order twice?").text.lower() + ask("any rows repeated twice?").text.lower())
        ask("tell me about quantity")
        other = ask("what about the other column?")
        self.assertNotIn("quantity", other.choices)
        self.assertIn("which one", other.text)


class BaselineTest(unittest.TestCase):
    """The same checks run, in the same order, for every file; which ones apply depends on its columns."""

    def run_on(self, name: str, text: str):
        path = Path(tempfile.mkdtemp()) / name
        path.write_text(text)
        facts = analyse(_file(path))
        return facts, {cat: BUILDERS[cat](facts) for cat in CAT_IDS}

    def ids(self, cards):
        return [c["id"] for cat in CAT_IDS for c in cards[cat]]

    def test_numbers_and_text(self):
        rng = random.Random(3)
        rows = "".join(f"{rng.gauss(50, 10):.1f},{rng.gauss(5, 1):.2f},{rng.randint(1, 9)},{rng.choice('abc')}\n"
                       for _ in range(300))
        facts, cards = self.run_on("a.csv", "x,y,z,group\n" + rows)
        ids = self.ids(cards)
        for card in ("detective-outliers", "detective-duplicates", "detective-types", "artist-distribution",
                     "artist-by-category", "artist-scatter", "artist-correlations", "scribe-summary",
                     "scribe-numbers", "scribe-categories", "coder-load", "janitor-missing"):
            self.assertIn(card, ids)
        hist = cards["artist"][0]
        self.assertEqual(hist["spec"], {"kind": "histogram", "column": "x", "bins": 10, "title": "x",
                                        "x_label": "x", "y_label": "count"})
        numbers = next(c for c in cards["scribe"] if c["id"] == "scribe-numbers")
        self.assertEqual([r[0] for r in numbers["table"]["rows"]], ["x", "y", "z"])
        self.assertAlmostEqual(numbers["table"]["rows"][0][4], round(facts.cols[0].stats["median"], 3))

    def test_text_only_file_skips_number_checks(self):
        _, cards = self.run_on("t.csv", "city,colour\n" + "".join(f"{c},{k}\n" for c in "pqr" for k in "uvw" * 5))
        ids = self.ids(cards)
        for card in ("artist-distribution", "artist-scatter", "artist-correlations", "scribe-numbers"):
            self.assertNotIn(card, ids)
        self.assertIn("scribe-categories", ids)

    def test_same_file_same_report(self):
        text = "a,b\n" + "".join(f"{i % 7},{i % 3}\n" for i in range(100))
        self.assertEqual(self.run_on("s.csv", text)[1], self.run_on("s.csv", text)[1])

    def test_closer_look_shows_its_evidence(self):
        rows = "".join(f"{v},{v * 2 + 0.01},{'' if i % 5 == 0 else 1}\n" for i, v in enumerate(list(range(1, 81)) + [2000] * 6))
        _, cards = self.run_on("e.csv", "spend,double,gap\n" + rows)
        extra = next(c for c in cards["scribe"] if c["id"] == "scribe-closer-look")
        self.assertIn("not run", extra["title"])
        evidence = " ".join(r[0] for r in extra["table"]["rows"])
        self.assertIn("r = 1.00", evidence)                           # spend and double move together
        self.assertIn("gap: 21% empty", evidence)                      # 18 of 86 rows
        self.assertIn("spend: mean", evidence)                        # the 900s pull the mean above the median


if __name__ == "__main__":
    unittest.main()
