"""Import checks: repeated headers, ragged rows and encodings are handled and reported, not hidden."""

import tempfile
import unittest
from pathlib import Path

from backend.engines.local import BUILDERS, analyse, redraw_scatter
from backend.files import FileInfo, Selection, inspect


def _info(name: str, data: bytes) -> FileInfo:
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(data)
    info = FileInfo("t", name, path, path.stat().st_size)
    inspect(info)
    return info


def _rows(n=30):
    return "".join(f"{i},{i * 3 % 17},{i % 5}\n" for i in range(n)).encode()


class DuplicateHeaderTest(unittest.TestCase):
    def test_repeated_names_become_unique_and_are_reported(self):
        info = _info("d.csv", b"amount,amount,amount\n" + _rows())
        self.assertEqual(info.columns, ["amount", "amount.1", "amount.2"])
        self.assertTrue(info.deduped)
        self.assertTrue(any("amount" in w and "renamed" in w for w in info.warnings))

    def test_a_name_that_already_exists_is_not_reused(self):
        info = _info("d.csv", b"a,a,a.1\n" + _rows())
        self.assertEqual(len(set(info.columns)), 3)
        self.assertEqual(info.columns[:2], ["a", "a.2"])

    def test_each_column_keeps_its_own_data(self):
        info = _info("d.csv", b"v,v,w\n" + _rows())
        facts = analyse(info)
        self.assertEqual([c.name for c in facts.cols], ["v", "v.1", "w"])
        self.assertNotEqual(facts.cols[0].stats["max"], facts.cols[1].stats["max"])
        card = redraw_scatter(info, Selection(), {"column_choices": ["v", "v.1", "w"]}, "v", "v.1")
        xs = {p[0] for p in card["chart"]["points"]}
        ys = {p[1] for p in card["chart"]["points"]}
        self.assertNotEqual(xs, ys)  # the second column is really the second column

    def test_clean_files_have_no_warnings(self):
        info = _info("ok.csv", b"a,b,c\n" + _rows())
        self.assertEqual(info.warnings, [])
        self.assertFalse(info.deduped)

    def test_exported_loaders_follow_the_renaming(self):
        facts = analyse(_info("d.csv", b"v,v,w\n" + _rows()))
        r = next(c for c in BUILDERS["detective"](facts) if c["code"].get("r"))["code"]["r"]
        self.assertIn("names(df) <- make.unique(names(df))", r)
        clean = analyse(_info("c.csv", b"v,u,w\n" + _rows()))
        r = next(c for c in BUILDERS["detective"](clean) if c["code"].get("r"))["code"]["r"]
        self.assertNotIn("make.unique", r)


class RaggedRowTest(unittest.TestCase):
    def test_extra_cells_are_reported(self):
        info = _info("r.csv", b"a,b\n1,2\n3,4,5\n6,7,8,9\n")
        self.assertEqual(info.preview[1], ["3", "4"])  # still ignored...
        self.assertTrue(any("2 row(s) have more cells" in w for w in info.warnings))  # ...but not silently
        self.assertTrue(any("data row 2, 3" in w for w in info.warnings))

    def test_short_rows_are_reported(self):
        info = _info("r.csv", b"a,b,c\n1,2,3\n4,5\n")
        self.assertTrue(any("stop before the last column" in w for w in info.warnings))

    def test_trailing_commas_and_blank_padding_are_fine(self):
        info = _info("r.csv", b"a,b\n1,2,\n3,4,,\n")
        self.assertEqual(info.warnings, [])


class EncodingTest(unittest.TestCase):
    def test_latin1_text_is_read_correctly_and_reported(self):
        info = _info("l.csv", "name,city\nCaf\u00e9,Z\u00fcrich\n".encode("cp1252"))
        self.assertEqual(info.preview, [["Caf\u00e9", "Z\u00fcrich"]])
        self.assertEqual(info.encoding, "cp1252")
        self.assertTrue(any("not valid UTF-8" in w for w in info.warnings))

    def test_utf8_and_bom_are_unchanged(self):
        for data in ("name\nCaf\u00e9\n".encode(), b"\xef\xbb\xbf" + "name\nCaf\u00e9\n".encode()):
            info = _info("u.csv", data)
            self.assertEqual(info.preview, [["Caf\u00e9"]])
            self.assertEqual((info.encoding, info.warnings), ("utf-8-sig", []))

    def test_utf16_is_unchanged(self):
        info = _info("u.csv", "name\nCaf\u00e9\n".encode("utf-16"))
        self.assertEqual(info.preview, [["Caf\u00e9"]])
        self.assertEqual((info.encoding, info.warnings), ("utf-16", []))

    def test_bytes_cp1252_cannot_decode_fall_back_to_latin1(self):
        info = _info("l.csv", b"a\nx\x81y\n")  # 0x81 is undefined in cp1252
        self.assertEqual(info.encoding, "latin-1")
        self.assertNotIn("\ufffd", info.preview[0][0])

    def test_exported_code_reads_the_file_the_same_way(self):
        facts = analyse(_info("l.csv", b"a,b\n" + "".join(f"{i},caf\xe9\n" for i in range(20)).encode("latin-1")))
        card = next(c for c in BUILDERS["detective"](facts) if c["code"].get("r"))["code"]
        self.assertIn('encoding="cp1252"', card["python"])
        self.assertIn('fileEncoding = "windows-1252"', card["r"])
        plain = analyse(_info("p.csv", b"a,b\n" + _rows(20)))
        card = next(c for c in BUILDERS["detective"](plain) if c["code"].get("r"))["code"]
        self.assertNotIn("encoding=", card["python"])
        self.assertIn('fileEncoding = "UTF-8-BOM"', card["r"])


if __name__ == "__main__":
    unittest.main()
