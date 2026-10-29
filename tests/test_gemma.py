"""Gemma engine: the Ollama client, checking model output, and how the chat falls back.

Run with: python -m unittest discover tests
The last test talks to a real Ollama and is skipped when none is running with gemma3:1b.
"""

import asyncio
import dataclasses
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from backend import api, engines
from backend.engines import gemma, lines
from backend.engines.gemma import (
    GemmaEngine,
    Ollama,
    OllamaError,
    canonical,
    check_claims,
    parse_tool,
)
from backend.engines.local import LocalEngine
from backend.files import FileInfo, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def _cafe(dir_: Path) -> FileInfo:
    path = dir_ / "cafe.csv"
    path.write_bytes(sample_csv())
    info = FileInfo("t", path.name, path, path.stat().st_size)
    inspect(info)
    return info


class FakeLLM:
    """Stands in for Ollama: answers from a function and records every prompt."""

    model = "gemma3:1b"

    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def chat(self, messages, schema=None, max_tokens=250):
        self.prompts.append((messages, schema))
        result = self.answer(messages, schema)
        if isinstance(result, Exception):
            raise result
        return result


class StubOllama(BaseHTTPRequestHandler):
    """A pretend Ollama on a free port. `mode` picks how it behaves."""

    mode = "ok"
    models = ["gemma3:1b"]

    def log_message(self, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except ConnectionError:
            pass  # the client gave up (the timeout test)

    def do_GET(self):
        self._json({"models": [{"name": m} for m in self.models]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.mode == "slow":
            time.sleep(1.5)
        if self.mode == "missing":
            return self._json({"error": f"model '{body['model']}' not found"}, 404)
        self._json(
            {
                "message": {"role": "assistant", "content": "hello from the stub"},
                "done": True,
            }
        )


class OllamaClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StubOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        StubOllama.mode, StubOllama.models = "ok", ["gemma3:1b"]

    def test_a_successful_request(self):
        llm = Ollama(self.url, "gemma3:1b", 5)
        self.assertIsNone(llm.check())
        self.assertEqual(
            llm.chat([{"role": "user", "content": "hi"}]), "hello from the stub"
        )

    def test_a_missing_model_says_how_to_get_it(self):
        StubOllama.mode, StubOllama.models = "missing", ["llama3.2:1b"]
        llm = Ollama(self.url, "gemma3:1b", 5)
        with self.assertRaises(OllamaError) as caught:
            llm.chat([{"role": "user", "content": "hi"}])
        self.assertIn("ollama pull gemma3:1b", str(caught.exception))

    def test_ollama_not_running(self):
        llm = Ollama("http://127.0.0.1:9", "gemma3:1b", 5)  # nothing listens on port 9
        with self.assertRaises(OllamaError) as caught:
            llm.chat([{"role": "user", "content": "hi"}])
        self.assertIn("not running", str(caught.exception))

    def test_a_timeout_then_no_waiting_on_the_next_message(self):
        StubOllama.mode = "slow"
        llm = Ollama(self.url, "gemma3:1b", 0.3)
        with self.assertRaises(OllamaError) as caught:
            llm.chat([{"role": "user", "content": "hi"}])
        self.assertIn("took more than", str(caught.exception))
        StubOllama.mode = "ok"
        start = time.monotonic()
        with self.assertRaises(OllamaError):  # still failing for RECHECK seconds...
            llm.chat([{"role": "user", "content": "hi"}])
        self.assertLess(time.monotonic() - start, 0.1)  # ...without another request
        llm.failed_at -= gemma.RECHECK
        self.assertEqual(
            llm.chat([{"role": "user", "content": "hi"}]), "hello from the stub"
        )

    def test_only_this_computer(self):
        with self.assertRaises(ValueError):
            Ollama("http://example.com:11434", "gemma3:1b", 5)


class EngineSelectionTest(unittest.TestCase):
    def pick(self, **changes):
        with (
            mock.patch.object(
                engines, "settings", dataclasses.replace(engines.settings, **changes)
            ),
            mock.patch.object(Ollama, "warm"),
        ):
            return engines.get_engine()

    def test_engines(self):
        self.assertIs(type(self.pick(engine="local")), LocalEngine)
        chosen = self.pick(
            engine="gemma",
            ollama_url="http://127.0.0.1:11434",
            ollama_model="gemma3:1b",
        )
        self.assertIs(type(chosen), GemmaEngine)
        self.assertEqual((chosen.name, chosen.llm.model), ("gemma", "gemma3:1b"))
        self.assertIs(
            type(self.pick(engine="gemma", ollama_url="http://10.0.0.5:11434")),
            LocalEngine,
        )  # not local: off
        self.assertIs(type(self.pick(engine="banana")), LocalEngine)


class ToolCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.engines.local import analyse

        cls.facts = analyse(_cafe(Path(tempfile.mkdtemp())))

    def tool(self, message, **data):
        return parse_tool(
            json.dumps({"column": "", "stat": "", **data}),
            self.facts,
            message,
            data.pop("last", ""),
        )

    def test_a_good_request_becomes_a_plain_question(self):
        route = self.tool(
            "whats the priciest unit price",
            tool="stat",
            column="unit_price",
            stat="max",
        )
        self.assertEqual(route["column"].name, "unit_price")
        self.assertEqual(canonical(route), "what is the highest unit_price?")

    def test_bad_requests_are_rejected(self):
        for raw in (
            "not json",
            "[]",
            '{"tool": "drop_column", "column": "total"}',
            '{"tool": "run_python"}',
            '{"tool": "stat", "column": "total", "stat": "variance"}',
            '{"tool": "histogram", "column": "total", "stat": ""}',  # charts are changed in their cards, not by the model
        ):
            self.assertIsNone(parse_tool(raw, self.facts, "total"), raw)
        self.assertIsNone(
            self.tool("price of gold", tool="stat", column="gold_price", stat="max")
        )  # no such column
        self.assertIsNone(
            self.tool("weather in paris", tool="stat", column="date", stat="min")
        )  # not in the message
        self.assertIsNone(
            self.tool("max please", tool="stat", column="", stat="")
        )  # stat without a stat

    def test_it_means_the_last_column(self):
        self.assertIsNotNone(
            self.tool("any gaps in it", tool="missing", column="rating", last="rating")
        )
        self.assertIsNone(
            self.tool("any gaps in it", tool="missing", column="rating", last="total")
        )

    def test_numbers_about_the_file_must_come_from_the_facts(self):
        facts = "File cafe.csv: 12063 rows. Data health 64/100. 1,501 cells are empty (1.0%)."
        names = ["total", "cafe.csv"]
        ok = "It has 12,063 rows and 1501 empty cells. There are 2 reasons, and Python 3 runs it."
        self.assertEqual(check_claims(ok, facts, names), (ok, 0))
        general = "Hold out the last 20% of the timeline. LSTMs often need 1000 steps of history."
        self.assertEqual(
            check_claims(general, facts, names), (general, 0)
        )  # general numbers are fine
        made_up = "The average total is 42.7. About 12,000 rows have gaps. A baseline comes first."
        self.assertEqual(
            check_claims(made_up, facts, names), ("A baseline comes first.", 2)
        )
        self.assertEqual(
            check_claims("Your data gets an R^2 of 0.83.", facts, names), ("", 1)
        )  # never computed
        self.assertEqual(
            check_claims("The total column has 7 missing values.", facts, names),
            ("", 1),
        )  # small, still false


class GemmaChatTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def engine(self, answer):
        llm = FakeLLM(answer)
        engine = GemmaEngine(0.01, llm)
        job = Job(id="j", file=_cafe(self.dir))
        asyncio.run(engine.run(job))
        return engine, job, llm, lambda m: asyncio.run(engine.chat(job, m))

    def test_why_questions_are_explained_from_the_facts(self):
        _engine, _job, llm, ask = self.engine(
            lambda m, s: "Pandas reads the table into a DataFrame so you can filter it."
        )
        reply = ask("why do I need pandas?")
        self.assertEqual([r.who for r in reply], ["coder"])
        self.assertIn("DataFrame", reply[0].text)
        system = llm.prompts[-1][0][0]["content"]
        self.assertRegex(
            system, r"pandas \(in [^)]*Load and peek"
        )  # read from the generated code
        self.assertIn("matplotlib (in Distribution of quantity", system)
        self.assertIn("pip install pandas matplotlib scikit-learn", system)
        self.assertNotIn("100000", system)  # a cell value: rows are never sent
        self.assertLess(len(system), 8000)

    def test_made_up_numbers_are_replaced_by_the_rules(self):
        _, _, _, ask = self.engine(
            lambda m, s: "The health score is 12 because 4,321 rows are broken."
        )
        replies = ask("why is the health score so low?")
        self.assertEqual(replies[0].text, lines.CHAT_GEMMA_UNCHECKED)
        self.assertIn("starts at 100", replies[1].text)  # the rules' (true) answer

    def test_ollama_down_falls_back_and_says_so_once(self):
        _, _, _, ask = self.engine(lambda m, s: OllamaError("ollama is not running"))
        first = ask("why do I need pandas?")
        self.assertIn("ollama is not running", first[0].text)
        self.assertIn("pip install", first[1].text)  # the rules still answer
        second = ask("why should i drop duplicates?")
        self.assertFalse(any("napping" in r.text for r in second))

    def test_a_lookup_is_answered_and_says_how_it_was_read(self):
        engine, _job, llm, ask = self.engine(
            lambda m, s: json.dumps(
                {"tool": "stat", "column": "customer_age", "stat": "min"}
            )
        )
        reply = ask("zap me the tiniest age")  # the rules don't read this one
        self.assertIsNotNone(llm.prompts[-1][1])  # asked for JSON with a schema
        self.assertIn(
            "(reading that as 'what is the lowest customer_age?')", reply[0].text
        )
        self.assertIn(
            f"The lowest customer_age is {engine._facts['j'].cols[8].stats['min']:.0f}",
            reply[0].text,
        )

    def test_chart_requests_never_reach_the_model(self):
        _, job, llm, ask = self.engine(lambda m, s: self.fail("the model was asked"))
        before = [dict(c) for c in job.results["artist"]]
        for message in ("make the histogram chunkier with 15 bins", "please switch the scatter plot to rating"):
            reply = ask(message)
            self.assertEqual(reply[0].who, "artist")
            self.assertIn(lines.CHAT_CHART_DIY, reply[0].text)
        self.assertEqual(job.results["artist"], before)
        self.assertEqual(llm.prompts, [])

    def test_a_guess_about_a_made_up_column_asks_instead(self):
        _, _, _, ask = self.engine(
            lambda m, s: json.dumps(
                {"tool": "stat", "column": "weather", "stat": "max"}
            )
        )
        self.assertEqual(
            ask("zorp the weather")[0].text, lines.CHAT_CLARIFY
        )  # no guess, no unrelated hint

    def test_simple_things_never_wait_for_the_model(self):
        _, _, llm, ask = self.engine(lambda m, s: self.fail("the model was asked"))
        self.assertIn(ask("thank youuu")[0].text, lines.CHAT_THANKS)
        self.assertIn(
            "The highest quantity is 250", ask("what is the highest quantity?")[0].text
        )
        self.assertIn(
            "gemma3:1b", ask("are you an AI?")[0].text
        )  # honest about the model
        self.assertEqual(llm.prompts, [])

    def test_general_questions_before_a_file(self):
        llm = FakeLLM(
            lambda m, s: "A z-score counts standard deviations from the mean."
        )
        replies = asyncio.run(GemmaEngine(0.01, llm).chat(None, "what is a z-score?"))
        self.assertIn("z-score", replies[0].text)
        self.assertIn("No file", llm.prompts[0][0][0]["content"])

    def test_history_stays_with_its_own_file(self):
        engine, _job, llm, ask = self.engine(lambda m, s: "Because of the gaps.")
        ask("tell me about rating")
        other = Job(id="k", file=_cafe(self.dir))
        asyncio.run(engine.run(other))
        sent = lambda: " ".join(m["content"] for m in llm.prompts[-1][0])
        asyncio.run(engine.chat(other, "why should i fill the gaps?"))
        self.assertNotIn("tell me about rating", sent())
        ask("why should i fill the gaps?")
        self.assertIn("tell me about rating", sent())

    def test_the_api_shape_is_unchanged(self):
        engine, job, _, _ = self.engine(lambda m, s: "fine")
        with (
            mock.patch.object(api, "engine", engine),
            mock.patch.object(api.jobs, "get", return_value=job),
        ):
            out = asyncio.run(
                api.chat(
                    api.ChatIn(job_id="j", message="use 20 bins for the histogram")
                )
            )
        reply = out["replies"][0]
        self.assertEqual(set(reply), {"from", "reply", "choices", "code", "followup"})
        self.assertIn(lines.CHAT_CHART_DIY, reply["reply"])


MODEL = engines.settings.ollama_model


def _ollama_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            return any(m["name"] == MODEL for m in json.load(r)["models"])
    except OSError:
        return False


@unittest.skipUnless(_ollama_ready(), f"Ollama with {MODEL} is not running")
class RealGemmaTest(unittest.TestCase):
    """The real model (OLLAMA_MODEL). Its wording changes between models and versions, so these only check that an
    answer arrives through the chat, from the right cat, about the right subject; they cannot prove it is correct."""

    @classmethod
    def setUpClass(cls):
        cls.engine = GemmaEngine(0.01, Ollama("http://127.0.0.1:11434", MODEL, 180))
        cls.job = Job(id="real", file=_cafe(Path(tempfile.mkdtemp())))
        asyncio.run(cls.engine.run(cls.job))

    def ask(self, message):
        return asyncio.run(self.engine.chat(self.job, message))

    def test_a_real_answer_reaches_the_chat(self):
        reply = self.ask("what's the difference between a mean and a median?")
        self.assertEqual(reply[0].who, "scribe")
        self.assertIn("median", reply[0].text.lower())
        self.assertGreater(len(reply[0].text), len(lines.CHAT_VOICE["scribe"]) + 20)

    def test_a_real_follow_up_stays_on_the_subject(self):
        self.ask("would an LSTM make sense for this data?")
        reply = self.ask("does it need a GPU?")
        self.assertEqual(reply[-1].who, "coder")
        self.assertRegex(reply[-1].text.lower(), r"gpu|cpu")


if __name__ == "__main__":
    unittest.main()
