"""Run with: python -m unittest discover tests"""

import asyncio
import csv
import random
import tempfile
import unittest
from pathlib import Path

from backend.engines import lines
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
            w.writerow(
                [f"num_{i}" for i in range(150)] + [f"cat_{i}" for i in range(50)]
            )
            for _ in range(500):
                w.writerow(
                    [
                        round(rng.gauss(0, 1), 3) if rng.random() > 0.05 else ""
                        for _ in range(150)
                    ]
                    + [rng.choice("abcde") for _ in range(50)]
                )
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
        store, quantity, total = (
            info.columns.index(c) for c in ("store", "quantity", "total")
        )
        everything = analyse(info)
        sel = Selection(
            columns=[store, quantity, total], target=total, exclude=[(store, "Campus")]
        )
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
            analyse(
                info,
                Selection(
                    exclude=[
                        (store, v)
                        for v in (
                            "Campus",
                            "Riverside",
                            "Old Town",
                            "Harbour",
                            "Station",
                            "CAMPUS",
                            "RIVERSIDE",
                            "OLD TOWN",
                            "HARBOUR",
                            "STATION",
                        )
                    ]
                ),
            )

    def test_none_is_a_value_not_a_missing_cell(self):
        path = self.dir / "holiday.csv"
        path.write_text("holiday,temp\nNone,1\nNone,2\nLabor Day,3\nNone,\nNA,5\n")
        facts = analyse(_file(path))
        holiday, temp = facts.cols
        self.assertEqual(
            (holiday.kind, holiday.missing, holiday.distinct), ("text", 1, 2)
        )  # only "NA" is missing
        self.assertEqual(holiday.top[0], ("None", 3))
        self.assertEqual(temp.missing, 1)
        code = BUILDERS["coder"](facts)[0]["code"]["python"]
        self.assertIn(
            "keep_default_na=False", code
        )  # pandas would otherwise turn "None" into NaN
        self.assertNotIn('"None"', code.split("na_values=")[1].split("]")[0])

    def test_exclude_treats_zero_and_zero_point_zero_alike(self):
        path = self.dir / "z.csv"
        path.write_text("n,label\n0,a\n0.0,b\n0.00,c\n1,d\n,e\n")
        info = _file(path)
        facts = analyse(info, Selection(exclude=[(0, "0")]))
        self.assertEqual(
            (facts.rows, facts.excluded_rows), (2, 3)
        )  # the blank cell is not zero
        facts = analyse(info, Selection(exclude=[(0, "0.0")]))
        self.assertEqual(facts.excluded_rows, 3)
        facts = analyse(info, Selection(exclude=[(1, "a")]))
        self.assertEqual(facts.excluded_rows, 1)
        self.assertIn(
            'pd.to_numeric(df["n"], errors="coerce") != 0.0',
            BUILDERS["coder"](analyse(info, Selection(exclude=[(0, "0")])))[0]["code"][
                "python"
            ],
        )

    def _chat(self, text: str):
        path = self.dir / "chat.csv"
        path.write_text(text)
        engine = LocalEngine(speed=0.05)
        job = Job(id="j", file=_file(path))
        asyncio.run(engine.run(job))
        return lambda m: asyncio.run(engine.chat(job, m))[
            0
        ]  # the first (usually only) reply

    def _cafe(self):
        path = self.dir / "cafe.csv"
        path.write_bytes(sample_csv())
        engine = LocalEngine(speed=0.05)
        job = Job(id="j", file=_file(path))
        asyncio.run(engine.run(job))
        return lambda m: asyncio.run(engine.chat(job, m))[
            0
        ]  # the first (usually only) reply

    def test_chat_routes_to_the_right_cat(self):
        ask = self._cafe()
        self.assertEqual(ask("any outliers in quantity?").who, "detective")
        self.assertIn("missing", ask("how much is missing in rating").text)
        self.assertEqual(ask("tell me about customer age").who, "scribe")
        self.assertEqual(ask("show me some code").who, "coder")
        self.assertEqual(ask("hello").who, "sloth")

    def test_chat_remembers_the_last_cat_and_column(self):
        ask = self._cafe()
        first = ask("any outliers in quantity?")
        self.assertEqual(first.who, "detective")
        self.assertIn("quantity has", first.text)
        again = ask("what about total?")  # a bare column keeps the detective
        self.assertEqual(again.who, "detective")
        self.assertIn("total has", again.text)
        ask("any outliers in rating?")
        missing = ask("is it missing anywhere?")  # "it" is rating
        self.assertEqual(missing.who, "janitor")
        self.assertIn("rating has", missing.text)
        ask("any outliers in quantity?")
        self.assertIn("Most extreme", ask("show me examples").text)

    def test_whole_file_answers_offer_columns_to_tap(self):
        ask = self._cafe()
        reply = ask("any outliers?")
        self.assertEqual(reply.who, "detective")
        self.assertTrue(reply.choices)
        follow = ask(reply.choices[0])  # tapping a choice sends its name
        self.assertEqual(follow.who, "detective")
        self.assertIn(f"{reply.choices[0]} has", follow.text)

    def test_cats_ask_before_guessing(self):
        ask = self._cafe()
        guess = ask(
            "tell me about customer"
        )  # only customer_age matches, but it is a guess
        self.assertEqual((guess.who, guess.choices), ("scribe", ["yes", "no"]))
        self.assertIn("customer_age", guess.text)
        self.assertIn("customer_age is a number column", ask("yes").text)
        ask("tell me about customer")
        self.assertEqual(ask("no").who, "sloth")  # declined: the sloth drops it
        stat = ask("what is the average?")  # no column named
        self.assertEqual(stat.choices[0], "quantity")
        self.assertIn("mean", ask("yes").text)
        ask("tell me about customer")
        self.assertEqual(
            ask("any duplicates?").who, "detective"
        )  # an unrelated question wins over the open one

    def test_cats_read_the_data_back(self):
        holidays = ["None"] * 30 + ["Labor Day"] * 3 + ["Christmas Day"] * 2
        ask = self._chat(
            "holiday,temp\n"
            + "\n".join(f"{h},{270 + i}" for i, h in enumerate(holidays))
            + "\n"
        )
        ask(
            "any outliers in temp?"
        )  # an earlier detective turn must not hijack the next question
        listing = ask(
            "owh, what holidays are there in the dataset, could you list them out for me"
        )
        self.assertEqual(listing.who, "scribe")
        self.assertIn("holiday has 3 distinct values", listing.text)
        self.assertIn("'None' (30)", listing.text)
        self.assertIn("'Labor Day' (3)", listing.text)
        self.assertIn("'Christmas Day' (2)", listing.text)
        again = ask(
            "and what values does it have?"
        )  # "it" is the holiday column from the last answer
        self.assertIn("holiday has 3 distinct values", again.text)
        self.assertIn(
            "appears 2 times in holiday", ask("how many Christmas Day are there?").text
        )
        columns = ask("what columns are there?")
        self.assertIn("holiday (text)", columns.text)
        self.assertIn("temp (number)", columns.text)
        self.assertEqual(columns.choices, ["holiday", "temp"])
        rows = ask("show me some rows")
        self.assertIn("row 1: holiday=None, temp=270", rows.text)
        self.assertEqual(
            ask("what types of holiday are there?").who, "scribe"
        )  # "types" is not a type problem

    def test_code_question_after_a_column_list_is_not_hijacked(self):
        """The reported conversation: list a column's values, then ask about the code."""
        rows = "".join(
            f"{w},{d},{20 + i},{100 + i * 3}\n"
            for i, (w, d) in enumerate(
                [
                    ("Clear", "sky is clear"),
                    ("Rain", "light rain"),
                    ("Clouds", "few clouds"),
                    ("Clear", "sunny"),
                ]
                * 5
            )
        )
        ask = self._chat(
            "weather_main,weather_description,temp,traffic_volume\n" + rows
        )
        vague = ask("can you list me the type of weather that exists?")
        self.assertEqual(vague.choices[-1], "all")
        self.assertIn("weather_main has 3 distinct values", ask("weather_main").text)
        seed = ask("about the code, what seed does it use?")
        self.assertEqual(seed.who, "coder")
        self.assertIn("random_state=42", seed.text)
        self.assertNotIn("distinct values", seed.text)

    def test_code_questions_are_answered_from_the_generated_code(self):
        ask = self._cafe()
        ask("any outliers in quantity?")  # "it" below must not mean the quantity column
        seed = ask("about the code, what seed does it use?")
        self.assertEqual(seed.who, "coder")
        self.assertIn(
            "`random_state=42`", seed.text
        )  # short code goes inline, in backticks
        self.assertEqual(seed.choices, [])  # a clear answer needs no follow-up buttons
        libs = ask("which libraries does the code use?").text
        self.assertIn("pandas", libs)
        self.assertRegex(libs, r"pip install .*pandas")
        self.assertIn(
            "scikit-learn", libs.split("pip install")[1]
        )  # sklearn is installed as scikit-learn
        self.assertIn("LinearRegression", ask("what model does the baseline use?").text)
        self.assertIn("test_size=0.2", ask("how is the data split for training?").text)
        load = ask("show me the code to load the data")
        self.assertIn(
            "pd.read_csv(", load.code["python"]
        )  # whole snippets go in a code box
        self.assertNotIn("pd.read_csv(", load.text)
        self.assertIn("cafe.csv", ask("how do I run this?").text)
        self.assertIn("ipynb", ask("can I get a notebook?").text)
        rcode = ask("is there R code?")
        self.assertIn("every snippet has an R version", rcode.text)
        self.assertEqual(rcode.code["lang"], "r")
        self.assertIn("read.csv(", rcode.code["r"])
        self.assertIn("set.seed(42)", ask("what seed does the R code use?").text)
        self.assertIn("base R only", ask("which libraries does the R code need?").text)
        self.assertIn("`lm`", ask("what model does the R code fit?").text)
        r_load = ask("show me the R code to load the data")
        self.assertEqual(r_load.code["lang"], "r")
        self.assertEqual(
            ask("show me the code to load the data").code["lang"], "python"
        )
        self.assertIn("read.csv", ask("how do I run this in R?").text)
        finder = ask("show me the code that finds outliers")
        self.assertEqual(finder.who, "detective")
        self.assertIn("quantile", finder.code["python"])
        self.assertEqual(
            ask("what score does the model get?").who, "coder"
        )  # "score" here is not the health score
        self.assertTrue(
            ask("tell me about the code").choices
        )  # a vague code question offers examples

    def _cafe_all(self):
        path = self.dir / "cafe.csv"
        path.write_bytes(sample_csv())
        engine = LocalEngine(speed=0.05)
        job = Job(id="j", file=_file(path))
        asyncio.run(engine.run(job))
        return lambda m: asyncio.run(engine.chat(job, m))

    def test_several_questions_get_several_answers(self):
        ask = self._cafe_all()
        replies = ask(
            "what is the highest quantity and how many duplicate rows are there?"
        )
        self.assertEqual([r.who for r in replies], ["scribe", "detective"])
        self.assertIn("The highest quantity is 250", replies[0].text)
        self.assertIn("63 duplicate rows", replies[1].text)
        same = ask(
            "what is the mean rating? what is the median rating?"
        )  # one cat, two answers
        self.assertEqual([r.who for r in same], ["scribe", "scribe"])
        self.assertTrue(same[0].text.startswith("*pushes up glasses*"))
        self.assertFalse(
            same[1].text.startswith("*pushes up glasses*")
        )  # the voice line is said once
        pair = ask(
            "highest quantity and lowest customer_age"
        )  # each column gets its own stat
        self.assertEqual(len(pair), 2)
        self.assertIn("highest quantity", pair[0].text)
        self.assertIn("lowest customer_age", pair[1].text)
        self.assertNotIn("lowest quantity", pair[0].text)

    def test_answers_give_only_what_was_asked(self):
        ask = self._cafe()
        top = ask("what is the highest quantity?").text
        self.assertIn("The highest quantity is 250", top)
        for other in ("median", "mean", "min ", "missing"):
            self.assertNotIn(other, top)
        both = ask("what are the highest and lowest customer_age?").text
        self.assertIn("lowest customer_age is 16", both)
        self.assertIn("highest customer_age", both)
        self.assertNotIn("median", both)
        self.assertIn("most common store", ask("what is the most common store?").text)
        self.assertIn(
            "earliest date is 2025-01-03", ask("what is the earliest date?").text
        )
        self.assertIn("not a number column", ask("what is the highest store?").text)
        self.assertRegex(ask("how many rows are there?").text, r"12,063 rows\.$")
        self.assertIn("12 columns.", ask("how many columns are there?").text)
        asked = ask("what is the highest value?")  # no column: the cat checks first
        self.assertEqual(asked.choices[0], "quantity")
        answer = ask("yes")
        self.assertIn("The highest quantity is 250", answer.text)
        self.assertNotIn("median", answer.text)

    def test_without_a_file_several_questions_get_one_hint(self):
        replies = asyncio.run(
            LocalEngine(speed=0.05).chat(
                None, "what is the max temp? and how many rows are there?"
            )
        )
        self.assertEqual([r.who for r in replies], ["sloth"])

    def test_buttons_and_askers_fit_the_question(self):
        ask = self._cafe()
        self.assertEqual(
            ask("how many duplicate rows are there?").choices, []
        )  # outlier columns don't fit here
        self.assertTrue(ask("any outliers?").choices)
        ask("show me the code to load the data")
        self.assertEqual(
            ask("tell me about customer").who, "scribe"
        )  # not the coder who spoke last

    def test_a_connecting_word_is_not_a_question(self):
        ask = self._cafe_all()
        replies = ask(
            "can you give me the code snippet to load the shape? and also are there any missing values in the dataset?"
        )
        self.assertEqual(
            [r.who for r in replies], ["coder", "janitor"]
        )  # no sloth hint in between
        self.assertIsNotNone(replies[0].code)
        mixed = ask(
            "show me some rows and zzzz qqqq"
        )  # a part nobody understands stays quiet
        self.assertEqual([r.who for r in mixed], ["scribe"])
        self.assertEqual(
            ask("zzzz qqqq")[0].who, "sloth"
        )  # ...unless it is the whole message

    def test_answers_to_a_cats_question_are_marked_as_follow_ups(self):
        ask = self._cafe()
        self.assertFalse(
            ask("tell me about customer").followup
        )  # the question itself is a new request
        self.assertTrue(ask("yes").followup)  # the answer to it is not
        ask("tell me about weather")  # no such column: a fresh question
        self.assertFalse(ask("any outliers in quantity?").followup)

    def test_small_talk_and_honesty(self):
        ask = self._cafe()
        self.assertEqual(ask("hi").who, "sloth")
        self.assertIn(
            ask("thanks!").text, lines.CHAT_THANKS
        )  # one of the sloth's replies
        self.assertIn("language model", ask("are you an AI?").text)
        self.assertIn("what columns are there?", ask("what can you do?").text)
        self.assertIn("closes eyes", ask("bye").text)
        self.assertEqual(
            ask("what is the capital of france?").who, "sloth"
        )  # off topic: a hint, not a data summary
        self.assertEqual(
            ask("hi, list the columns").who, "scribe"
        )  # a greeting does not swallow a real question

    def test_health_score_can_be_explained_and_repeated(self):
        ask = self._cafe()
        self.assertIn("starts at 100", ask("how is the health score calculated?").text)
        self.assertIn("health score is", ask("what's the health score?").text)
        first = ask("any outliers in quantity?")
        self.assertEqual(ask("say that again").text, first.text)

    def test_cards_answer_questions_about_themselves(self):
        ask = self._cafe()
        histogram = ask("what does the histogram show?")
        self.assertEqual(histogram.who, "artist")
        self.assertIn("histogram", histogram.text)
        dupes = ask("how many duplicate rows are there?")
        self.assertEqual(dupes.who, "detective")
        self.assertIn("63 duplicate rows", dupes.text)
        self.assertIn(
            "Full cleaning recipe", ask("tell me about the cleaning recipe").text
        )
        self.assertIn("scatter", ask("is there a scatter plot?").text.lower())

    def test_listing_values_after_a_vague_column_asks_first(self):
        ask = self._chat(
            "weather_main,weather_description\nClear,sky\nClear,sunny\nRain,wet\n"
        )
        self.assertEqual(ask("list the weather").choices[-1], "all")
        self.assertIn(
            "weather_main has 2 distinct values", ask("weather_main").text
        )  # the list intent survives the question

    def test_cats_list_ambiguous_columns(self):
        ask = self._chat(
            "weather_main,weather_description,n\nClear,sky,1\nRain,wet,2\n"
        )
        many = ask("tell me about weather")
        self.assertEqual(
            sorted(many.choices), ["all", "weather_description", "weather_main"]
        )
        self.assertEqual(
            ask("yes").choices, many.choices
        )  # "yes" to a list: asks again
        self.assertIn("weather_main is text", ask("weather_main").text)


if __name__ == "__main__":
    unittest.main()
