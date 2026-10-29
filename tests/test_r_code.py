"""Runs the generated R for real. Skipped when Rscript is not installed.

Run with: python -m unittest discover tests
"""

import glob
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.cats import CAT_IDS
from backend.engines.local import BUILDERS, analyse
from backend.exporters import build_r_script
from backend.files import FileInfo, Selection, inspect
from backend.jobs import Job
from backend.sample_data import sample_csv


def find_rscript() -> str | None:
    return shutil.which("Rscript") or next(
        iter(sorted(glob.glob("C:/Program Files/R/R-*/bin/Rscript.exe"))[::-1]), None
    )


RSCRIPT = find_rscript()


@unittest.skipUnless(RSCRIPT, "Rscript is not installed")
class GeneratedRTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def run_r(self, filename: str, content: bytes, select) -> str:
        """Analyse the file, write the R script the zip would contain, run it. Returns what R printed."""
        path = self.dir / filename
        path.write_bytes(content)
        info = FileInfo("t", filename, path, path.stat().st_size)
        inspect(info)
        facts = analyse(info, select(info) if select else None)
        job = Job(id="j", file=info)
        job.results = {cat: BUILDERS[cat](facts) for cat in CAT_IDS}
        script = build_r_script(job)
        (self.dir / "analysis.R").write_text(script, encoding="utf-8")
        done = subprocess.run(
            [RSCRIPT, "--vanilla", "analysis.R"],
            check=False,  # the assert below reports R's error output instead
            cwd=self.dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        self.assertEqual(
            done.returncode,
            0,
            f"R failed:\n{done.stderr[-1500:]}\n--- script ---\n{script}",
        )
        return done.stdout

    def test_sample_runs_end_to_end(self):
        out = self.run_r("cafe.csv", sample_csv(), None)
        self.assertIn("12063 rows, 12 columns", out)
        self.assertIn(
            "646 suspicious rows", out
        )  # the same counts the Python engine reports
        self.assertIn("63 duplicate rows", out)
        self.assertIn("R^2:", out)  # the baseline model ran on a number target
        self.assertTrue(
            (self.dir / "cafe_clean.csv").exists()
        )  # the cleaning recipe wrote its file
        self.assertTrue((self.dir / "Rplots.pdf").exists())  # and the charts were drawn

    def test_text_target_uses_a_classifier(self):
        def pick(info):
            keep = [
                info.columns.index(c)
                for c in ("store", "quantity", "unit_price", "rating", "category")
            ]
            return Selection(columns=keep, target=info.columns.index("store"))

        out = self.run_r("cafe.csv", sample_csv(), pick)
        self.assertIn("accuracy:", out)

    def test_filters_columns_and_none_values(self):
        rows = "holiday,temp,rain,note\n" + "".join(
            f"{'None' if i % 7 else 'Labor Day'},{270 + i % 20},{'0.0' if i % 3 else '1.5'},{'x' if i % 5 else ''}\n"
            for i in range(120)
        )

        def pick(info):
            c = info.columns.index
            return Selection(
                columns=[c("holiday"), c("temp"), c("rain")],
                target=c("temp"),
                exclude=[(c("holiday"), "Labor Day"), (c("rain"), "0")],
            )

        out = self.run_r("weather.csv", rows.encode(), pick)
        self.assertIn(
            "34 rows, 3 columns", out
        )  # 120 rows minus Labor Day minus every rain of 0 / 0.0

    def test_tsv_and_wide_files(self):
        header = "\t".join([f"num_{i}" for i in range(40)] + ["group"])
        body = "".join(
            "\t".join(
                [str((r * 7 + i) % 50) for i in range(40)] + [("a", "b", "c")[r % 3]]
            )
            + "\n"
            for r in range(300)
        )
        out = self.run_r("wide.tsv", (header + "\n" + body).encode(), None)
        self.assertIn("300 rows, 41 columns", out)


if __name__ == "__main__":
    unittest.main()
