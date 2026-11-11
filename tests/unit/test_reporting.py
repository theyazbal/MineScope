import csv
import io
import json
import os
import tempfile
import unittest

from minescope.core.errors import ReportError
from minescope.models.server import ScanResult
from minescope.reporting import render_csv, render_html, render_json, write_report

ON = ScanResult("Main", "play.test", 25565, "java", True, 12.5, "1.21", 767, "Hello", 2, 20, ["A", "B"])
OFF = ScanResult("Down", "x.test", 19132, "bedrock", False, error="Connection timed out")


class ReportingTests(unittest.TestCase):
    def test_json(self):
        doc = json.loads(render_json([ON, OFF]))
        self.assertEqual(doc["count"], 2)
        self.assertEqual(doc["organization"], "DevStudio")
        self.assertEqual(doc["results"][0]["player_names"], ["A", "B"])
        self.assertEqual(doc["results"][0]["address"], "play.test:25565")
        self.assertFalse(doc["results"][1]["online"])

    def test_csv_rows_and_header(self):
        rows = list(csv.DictReader(io.StringIO(render_csv([ON, OFF]))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["player_names"], "A;B")
        self.assertEqual(rows[1]["error"], "Connection timed out")
        self.assertEqual(render_csv([]).count("\n"), 1)  # header only

    def test_csv_formula_injection_neutralized(self):
        evil = ScanResult("=HYPERLINK(\"x\")", "h.test", 1, "java", True, motd="@SUM(1)", player_names=["+cmd"])
        rows = list(csv.DictReader(io.StringIO(render_csv([evil]))))
        self.assertTrue(rows[0]["name"].startswith("'="))
        self.assertTrue(rows[0]["motd"].startswith("'@"))

    def test_html_escaping_and_content(self):
        evil = ScanResult("<script>alert(1)</script>", "h.test", 1, "java", True, motd="<img src=x onerror=1>",
                          player_names=["<b>n</b>"])
        out = render_html([evil, OFF])
        self.assertNotIn("<script>alert", out)
        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("ONLINE", out)
        self.assertIn("OFFLINE", out)
        self.assertIn("1 of 2 servers online", out)
        self.assertIn("DevStudio", out)

    def test_write_report_all_formats(self):
        d = tempfile.mkdtemp()
        for fmt in ("json", "csv", "html"):
            p = write_report([ON], fmt, os.path.join(d, "out"), stem="r1")
            self.assertTrue(p.exists())
            self.assertEqual(p.suffix, "." + fmt)
        self.assertEqual([f for f in os.listdir(os.path.join(d, "out")) if f.endswith(".tmp")], [])

    def test_name_sanitized_no_traversal(self):
        d = tempfile.mkdtemp()
        p = write_report([ON], "json", d, stem="../../evil")
        self.assertEqual(p.parent, __import__("pathlib").Path(d))
        self.assertEqual(p.name, "evil.json")

    def test_errors(self):
        with self.assertRaises(ReportError):
            write_report([ON], "pdf", tempfile.mkdtemp())
        with self.assertRaises(ReportError):
            write_report([ON], "json", tempfile.mkdtemp(), stem="///")
        blocker = os.path.join(tempfile.mkdtemp(), "file")
        open(blocker, "w").close()
        with self.assertRaises(ReportError):
            write_report([ON], "json", os.path.join(blocker, "sub"))


if __name__ == "__main__":
    unittest.main()
