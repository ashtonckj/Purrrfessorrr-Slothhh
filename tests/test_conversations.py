"""Regression tests from real conversations on the Metro traffic data (here a small synthetic file of the same shape).

The model is a stand-in that records what it was sent, so these check routing, context and safety, not
the model's wording. Run with: python -m unittest discover tests
"""

import asyncio
import json
import random
import tempfile
import unittest
from pathlib import Path

from backend.engines import lines
from backend.engines.gemma import GemmaEngine, OllamaError
from backend.files import FileInfo, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def traffic_csv(path: Path) -> FileInfo:
    rng = random.Random(7)
    rows = ["holiday,temp,rain_1h,weather_main,date_time,traffic_volume"]
    for h in range(600):
        day, hour = divmod(h, 24)
        rows.append(
            f"None,{270 + rng.random() * 30:.2f},{rng.choice([0, 0, 0, 0.5])},{rng.choice(['Clear', 'Clouds', 'Snow'])},"
            f"2016-{1 + day // 28:02d}-{1 + day % 28:02d} {hour:02d}:00:00,{1000 + 200 * hour + rng.randint(0, 500)}"
        )
    path.write_text("\n".join(rows) + "\n")
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return info


class Model:
    """A stand-in for Gemma. `text` answers discussions; `tool` answers JSON tool requests."""

    model = "gemma3:4b"

    def __init__(self, text="LSTMs learn patterns in sequences.", tool=None):
        self.text, self.tool, self.calls = (
            text,
            tool or {"tool": "unclear", "column": "", "stat": "", "bins": 0},
            [],
        )

    def chat(self, messages, schema=None, max_tokens=250):
        self.calls.append({"messages": messages, "json": schema is not None})
        answer = json.dumps(self.tool) if schema else self.text
        if (
            isinstance(answer, Exception)
            or isinstance(self.text, Exception)
            and not schema
        ):
            raise self.text
        return answer

    def sent(self, i=-1) -> str:
        return "\n".join(m["content"] for m in self.calls[i]["messages"])


class TrafficConversationTest(unittest.TestCase):
    def setUp(self):
        self.model = Model()
        self.engine = GemmaEngine(0.01, self.model)
        self.job = Job(
            id="traffic",
            file=traffic_csv(
                Path(tempfile.mkdtemp()) / "Metro_Interstate_Traffic_Volume.csv"
            ),
        )
        asyncio.run(self.engine.run(self.job))

    def ask(self, message, job=None):
        return asyncio.run(self.engine.chat(job or self.job, message))

    def assertNoGenericFallback(self, replies):
        summary = next(
            c["description"]
            for c in self.job.results["scribe"]
            if c["id"] == "scribe-summary"
        )
        for r in replies:
            self.assertFalse(r.text.startswith("mmh... i only delegate"), r.text)
            self.assertNotIn(summary, r.text)

    # 1, 2: libraries
    def test_why_pandas_is_explained_with_the_real_imports(self):
        self.model.text = "pandas holds the table as a DataFrame."
        reply = self.ask("why do i need to install pandas?")
        self.assertEqual([r.who for r in reply], ["coder"])
        self.assertIn("DataFrame", reply[0].text)
        self.assertRegex(self.model.sent(), r"pandas \(in [^)]*Load and peek")

    def test_matplotlib_and_tensorflow_come_from_the_generated_code(self):
        yes = self.ask("do i have to install matplotlib too?")[0]
        self.assertEqual(yes.who, "coder")
        self.assertIn("yes: Distribution of", yes.text)
        self.assertIn("`pip install matplotlib`", yes.text)
        no = self.ask("do i need tensorflow?")[0]
        self.assertTrue(
            no.text.split(": ", 1)[1].startswith(
                "no: none of the generated snippets import tensorflow"
            )
        )
        self.assertEqual(self.model.calls, [])  # facts about the code need no model

    # 3, 4, 5, 7: model choice and its follow-ups
    def test_model_choice_and_lstm_follow_ups_keep_the_thread(self):
        self.model.text = (
            "It depends on the target and metric; start from the linear baseline."
        )
        best = self.ask(
            "what is the best machine learning model to be used for this dataset?"
        )
        self.assertEqual(best[0].who, "coder")
        self.assertIn(
            "start from the linear baseline", best[0].text
        )  # Gemma's answer, not the baseline card
        facts = self.model.sent()
        self.assertIn("Target: traffic_volume, not picked by the user", facts)
        self.assertIn("Task: regression", facts)
        self.assertIn("Time column: date_time, from 2016-01-01 to", facts)
        self.assertIn(
            "splits rows at random", facts
        )  # so a time-based split can be advised

        self.model.text = "LSTMs suit sequences like hourly traffic, but compare them with the baseline."
        lstm = self.ask("does using LSTM make sense too?")
        self.assertEqual(lstm[0].who, "coder")
        self.assertNoGenericFallback(lstm)
        turns = self.model.calls[-1]["messages"]
        self.assertEqual(
            turns[1]["content"],
            "what is the best machine learning model to be used for this dataset?",
        )
        self.assertIn(
            "start from the linear baseline", turns[2]["content"]
        )  # the earlier answer goes along

        self.model.text = "It can use the hourly rhythm in traffic_volume."
        benefit = self.ask("what does LSTM benefit from this dataset")
        self.assertEqual(benefit[0].who, "coder")
        self.assertNoGenericFallback(benefit)
        self.assertIn("does using LSTM make sense too?", self.model.sent())

        self.model.text = "Not for this size; a CPU is fine to start."
        gpu = self.ask("does it need a GPU?")  # no ML word: a follow-up
        self.assertEqual(gpu[0].who, "coder")
        self.assertIn("what does LSTM benefit from this dataset", self.model.sent())

    # 6: off-topic
    def test_a_general_question_unrelated_to_the_data(self):
        self.model.text = "Paris."
        reply = self.ask("what's the capital of france?")
        self.assertEqual(reply[0].text.split(": ", 1)[1], "Paris.")
        self.assertNoGenericFallback(reply)

    # 8, 9: the rules still do the sure things, without the model
    def test_statistics_and_chart_edits_never_ask_the_model(self):
        self.model.text = AssertionError("the model was asked")
        top = self.ask("what is the highest traffic_volume?")[0]
        expected = max(
            int(r.split(",")[-1])
            for r in self.job.file.path.read_text().splitlines()[1:]
        )
        self.assertIn(f"The highest traffic_volume is {expected:,}", top.text)
        edit = self.ask("Change the histogram to 30 bins.")[0]
        self.assertEqual(edit.card["spec"]["bins"], 30)
        self.assertEqual(self.model.calls, [])

    def test_general_words_do_not_trigger_chart_edits(self):
        self.ask("what are the limitations of a histogram with too many bins?")
        hist = next(
            c for c in self.job.results["artist"] if c["id"] == "artist-distribution"
        )
        self.assertEqual(hist["spec"]["bins"], 10)

    # 10: ambiguity
    def test_a_vague_follow_up_gets_a_question_back(self):
        self.ask("which additional analysis would be useful?")
        reply = self.ask("is it ok?")
        self.assertEqual((reply[0].who, reply[0].text), ("sloth", lines.CHAT_CLARIFY))
        self.assertTrue(reply[0].choices)

    # 11, 14: model down
    def test_model_down_never_means_an_unrelated_answer(self):
        self.model.text = OllamaError("ollama is not running at http://127.0.0.1:11434")
        reply = self.ask("does using LSTM make sense too?")
        self.assertEqual(len(reply), 1)
        self.assertIn("question for my language model", reply[0].text)
        self.assertIn("ollama is not running", reply[0].text)
        self.assertNoGenericFallback(reply)
        stat = self.ask("why is the health score not 100?")  # rules can answer this one
        self.assertIn("starts at 100", stat[-1].text)

    # 12: invented numbers
    def test_invented_dataset_numbers_are_not_shown(self):
        self.model.text = (
            "This dataset has 99,999 rows and the model would score an R^2 of 0.93. "
            "LSTMs usually need long histories, such as 168 hourly steps."
        )
        reply = self.ask("would an LSTM be useful here?")[0]
        self.assertNotIn("99,999", reply.text)
        self.assertNotIn("0.93", reply.text)
        self.assertIn("168 hourly steps", reply.text)  # a general number may stay
        self.assertIn(lines.CHAT_GEMMA_TRIMMED, reply.text)
        true_rows = self.engine._facts["traffic"].rows
        self.model.text = f"Your file has {true_rows} rows."
        self.assertIn(
            f"{true_rows} rows",
            self.ask("is this dataset big enough for deep learning?")[0].text,
        )

    # 13: no leaks between files
    def test_context_stays_with_its_own_file(self):
        self.ask("does using LSTM make sense too?")
        cafe_path = Path(tempfile.mkdtemp()) / "cafe.csv"
        cafe_path.write_bytes(sample_csv())
        info = FileInfo("c", cafe_path.name, cafe_path, cafe_path.stat().st_size)
        inspect(info)
        cafe = Job(id="cafe", file=info)
        asyncio.run(self.engine.run(cafe))
        self.ask("why would I use a random forest?", job=cafe)
        sent = self.model.sent()
        self.assertIn("File cafe.csv", sent)
        self.assertNotIn("Metro_Interstate", sent)
        self.assertNotIn("traffic_volume", sent)
        self.assertNotIn("LSTM", sent)  # the other chat's history stays there


if __name__ == "__main__":
    unittest.main()
