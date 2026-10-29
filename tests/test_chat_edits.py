"""Chart edits from the chat, typo-proof questions, and the baseline EDA being the same for every file.

These need no language model: they are the rules every engine shares.
Run with: python -m unittest discover tests
"""

import asyncio
import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from backend.cats import CAT_IDS
from backend.engines import lines, talk
from backend.engines.local import BUILDERS, LocalEngine, analyse
from backend.files import FileInfo, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def _file(path: Path) -> FileInfo:
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return info


class ChartRequestTest(unittest.TestCase):
    """The chat no longer redraws charts: it points to the chart cards' dropdowns and changes nothing."""

    def setUp(self):
        path = Path(tempfile.mkdtemp()) / "cafe.csv"
        path.write_bytes(sample_csv())
        self.engine = LocalEngine(speed=0.02)
        self.job = Job(id="j", file=_file(path))
        asyncio.run(self.engine.run(self.job))

    def ask(self, message):
        return asyncio.run(self.engine.chat(self.job, message))[0]

    def test_change_requests_point_to_the_dropdowns(self):
        before = [dict(c) for c in self.job.results["artist"]]
        upload = hashlib.sha256(self.job.file.path.read_bytes()).hexdigest()
        for message in ("Change the histogram to 30 bins.", "can you make the histogram use more bins?",
                        "show me the distribution of total", "change this chart to a box plot",
                        "can you change the chart title and axis labels?", "switch the scatter plot to rating"):
            with self.subTest(message=message):
                reply = self.ask(message)
                self.assertEqual((reply.who, reply.text), ("artist", f"{lines.CHAT_VOICE['artist']} {lines.CHAT_CHART_DIY}"))
        self.assertEqual(self.job.results["artist"], before)         # nothing was redrawn
        self.assertEqual(hashlib.sha256(self.job.file.path.read_bytes()).hexdigest(), upload)

    def test_questions_about_charts_are_still_answered(self):
        reply = self.ask("what does the histogram show?")
        self.assertEqual(reply.who, "artist")
        self.assertIn("histogram", reply.text)
        self.assertNotIn(lines.CHAT_CHART_DIY, reply.text)


class NormaliseTest(unittest.TestCase):
    def test_stretched_words_and_typos(self):
        known = {"total", "unit", "price", "rating"}
        self.assertEqual(talk.normalise("thank youuu", known), "thank you")
        self.assertEqual(talk.normalise("Thanksss!!", known), "thanks!!")
        self.assertEqual(talk.normalise("coool", known), "cool")
        self.assertEqual(
            talk.normalise("whats the avrage totl", known), "whats the average total"
        )
        self.assertEqual(talk.normalise("weird prices", known), "weird price")
        self.assertEqual(
            talk.normalise("show the histgram", known), "show the histogram"
        )
        self.assertEqual(
            talk.normalise("this is fine", known), "this is fine"
        )  # real words stay
        self.assertEqual(
            talk.normalise("is it big enough for deep learning", known),
            "is it big enough for deep learning",
        )  # not "deep cleaning"

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
        self.assertIn(
            "duplicate",
            ask("same order twice?").text.lower()
            + ask("any rows repeated twice?").text.lower(),
        )
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
        rows = "".join(
            f"{rng.gauss(50, 10):.1f},{rng.gauss(5, 1):.2f},{rng.randint(1, 9)},{rng.choice('abc')}\n"
            for _ in range(300)
        )
        facts, cards = self.run_on("a.csv", "x,y,z,group\n" + rows)
        ids = self.ids(cards)
        for card in (
            "detective-outliers",
            "detective-duplicates",
            "detective-types",
            "artist-distribution",
            "artist-by-category",
            "artist-scatter",
            "artist-correlations",
            "scribe-summary",
            "scribe-numbers",
            "scribe-categories",
            "coder-load",
            "janitor-missing",
        ):
            self.assertIn(card, ids)
        hist = cards["artist"][0]
        self.assertEqual(hist["spec"], {"column": "x", "bins": 10})
        self.assertEqual(hist["column_choices"], ["x", "y", "z"])
        numbers = next(c for c in cards["scribe"] if c["id"] == "scribe-numbers")
        self.assertEqual([r[0] for r in numbers["table"]["rows"]], ["x", "y", "z"])
        self.assertAlmostEqual(
            numbers["table"]["rows"][0][4], round(facts.cols[0].stats["median"], 3)
        )

    def test_text_only_file_skips_number_checks(self):
        _, cards = self.run_on(
            "t.csv",
            "city,colour\n" + "".join(f"{c},{k}\n" for c in "pqr" for k in "uvw" * 5),
        )
        ids = self.ids(cards)
        for card in (
            "artist-distribution",
            "artist-scatter",
            "artist-correlations",
            "scribe-numbers",
        ):
            self.assertNotIn(card, ids)
        self.assertIn("scribe-categories", ids)

    def test_same_file_same_report(self):
        text = "a,b\n" + "".join(f"{i % 7},{i % 3}\n" for i in range(100))
        self.assertEqual(self.run_on("s.csv", text)[1], self.run_on("s.csv", text)[1])

    def test_closer_look_shows_its_evidence(self):
        rows = "".join(
            f"{v},{v * 2 + 0.01},{'' if i % 5 == 0 else 1}\n"
            for i, v in enumerate(list(range(1, 81)) + [2000] * 6)
        )
        _, cards = self.run_on("e.csv", "spend,double,gap\n" + rows)
        extra = next(c for c in cards["scribe"] if c["id"] == "scribe-closer-look")
        self.assertIn("not run", extra["title"])
        evidence = " ".join(r[0] for r in extra["table"]["rows"])
        self.assertIn("r = 1.00", evidence)  # spend and double move together
        self.assertIn("gap: 21% empty", evidence)  # 18 of 86 rows
        self.assertIn(
            "spend: mean", evidence
        )  # the 900s pull the mean above the median


if __name__ == "__main__":
    unittest.main()
