"""Hostile-looking file names and column headers must not change what the exported R script does."""

import unittest
from pathlib import Path

from backend.engines.rcode import q
from backend.exporters import build_r_script
from backend.files import FileInfo
from backend.jobs import Job

SEPARATORS = ["\n", "\r", "\r\n", "\x0b", "\x0c", "\x85", "\u2028", "\u2029"]


def _script(filename: str, title: str) -> str:
    job = Job(id="j", file=FileInfo("j", filename, Path("a.csv"), 0))
    job.results["artist"] = [
        {"id": "x", "title": title, "description": "", "code": {"r": "x <- 1"}}
    ]
    return build_r_script(job)


class RScriptCommentsTest(unittest.TestCase):
    def test_title_cannot_break_out_of_its_comment(self):
        for sep in SEPARATORS:
            with self.subTest(sep=repr(sep)):
                script = _script("data.csv", f"amount{sep}system('echo pwned')")
                code_lines = [
                    line
                    for line in script.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
                self.assertEqual(code_lines, ["x <- 1"])

    def test_file_name_cannot_break_out_of_its_comment(self):
        for sep in SEPARATORS:
            with self.subTest(sep=repr(sep)):
                script = _script(f"data{sep}system('echo pwned').csv", "ok")
                self.assertNotIn("system(", "".join(
                    line for line in script.splitlines() if not line.lstrip().startswith("#")
                ))

    def test_control_characters_are_dropped(self):
        script = _script("data.csv", "a\x00b\x1bc")
        self.assertNotIn("\x00", script)
        self.assertNotIn("\x1b", script)

    def test_normal_titles_are_unchanged(self):
        self.assertIn("# --- artist: Distribution of price", _script("data.csv", "Distribution of price"))


class RStringTest(unittest.TestCase):
    def test_quotes_backslashes_and_newlines_stay_inside_the_literal(self):
        self.assertEqual(q('a"b'), '"a\\"b"')
        self.assertEqual(q("a\\b"), '"a\\\\b"')
        self.assertEqual(q("a\nb"), '"a\\nb"')

    def test_astral_characters_use_an_escape_r_understands(self):
        self.assertEqual(q("\U0001f600"), '"\\U{1f600}"')  # not a surrogate pair
        self.assertEqual(q("caf\u00e9"), '"caf\\u00e9"')

    def test_text_that_looks_like_an_escape_is_not_rewritten(self):
        self.assertEqual(q("\\ud83d\\ude00"), '"\\\\ud83d\\\\ude00"')


if __name__ == "__main__":
    unittest.main()
