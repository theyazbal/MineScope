import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from minescope.cli.app import EXIT_ERROR, EXIT_OFFLINE, EXIT_OK, EXIT_USAGE, build_parser, main
from tests.fixtures.loopback import LoopbackJava, closed_port


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--plain", *argv])
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = str(self.dir / "t.db")
        self.reports = str(self.dir / "reports")

    def test_about_shows_real_project_info(self):
        code, out, _ = run("about")
        self.assertEqual(code, EXIT_OK)
        for text in ("MineScope", "DevStudio", "TheYAZBAL", "1.0.0"):
            self.assertIn(text, out)

    def test_parser_version(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()) as out:
            build_parser().parse_args(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_scan_history_stats_report_flow(self):
        with LoopbackJava() as srv:
            addr = f"127.0.0.1:{srv.port}"
            code, out, _ = run("--db", self.db, "scan", addr, "-e", "java", "-t", "2", "--no-query",
                               "-r", "json", "-r", "csv", "-r", "html", "-o", self.reports)
            self.assertEqual(code, EXIT_OK, out)
            self.assertIn("ONLINE", out)
            self.assertIn("Alice, Bob", out)
            self.assertEqual(sorted(p.suffix for p in Path(self.reports).iterdir()), [".csv", ".html", ".json"])
            run("--db", self.db, "scan", addr, "-e", "java", "--no-query")
            code, out, _ = run("--db", self.db, "history", addr, "-e", "java")
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(out.count("ONLINE"), 2)
            code, out, _ = run("--db", self.db, "stats", addr)
            self.assertIn("100.0%", out)
            code, out, _ = run("--db", self.db, "report", "json", "-o", self.reports)
            self.assertEqual(code, EXIT_OK)
            newest = max(Path(self.reports).glob("*.json"), key=os.path.getmtime)
            self.assertEqual(json.loads(newest.read_text())["count"], 1)

    def test_offline_and_fail_offline_exit_code(self):
        addr = f"127.0.0.1:{closed_port()}"
        code, out, _ = run("--db", self.db, "scan", addr, "-e", "java", "-t", "1")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("OFFLINE", out)
        code, _, _ = run("--db", self.db, "scan", addr, "-e", "java", "-t", "1", "--fail-offline")
        self.assertEqual(code, EXIT_OFFLINE)

    def test_no_save_does_not_write_history(self):
        addr = f"127.0.0.1:{closed_port()}"
        run("--db", self.db, "scan", addr, "-e", "java", "-t", "1", "--no-save")
        code, out, _ = run("--db", self.db, "history", addr, "-e", "java")
        self.assertIn("No stored history", out)

    def test_validation_errors_use_usage_exit_code(self):
        for argv in (["scan", "bad host!"], ["scan", "x.test:99999"], ["scan"],
                     ["scan", "x.test", "-t", "0"], ["history", "x.test", "--since", "zzz"],
                     ["-c", str(self.dir / "nope.json"), "scan", "x.test"]):
            code, out, _ = run("--db", self.db, *argv)
            self.assertEqual(code, EXIT_USAGE, argv)
            self.assertIn("Error", out)

    def test_config_init_show_and_scan_from_config(self):
        cfg = self.dir / "minescope.json"
        code, _, _ = run("config", "init", str(cfg))
        self.assertEqual(code, EXIT_OK)
        code, out, _ = run("config", "init", str(cfg))
        self.assertEqual(code, EXIT_ERROR)
        code, out, _ = run("-c", str(cfg), "config", "show")
        self.assertEqual(json.loads(out)["settings"]["timeout"], 3.0)
        with LoopbackJava() as srv:
            cfg.write_text(json.dumps({"settings": {"timeout": 2, "try_query": False},
                                       "servers": [{"name": "Local", "edition": "java",
                                                    "address": f"127.0.0.1:{srv.port}"}]}))
            code, out, _ = run("-c", str(cfg), "--db", self.db, "scan")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Local", out)

    def test_corrupt_config_is_reported(self):
        bad = self.dir / "bad.json"
        bad.write_text("{nope")
        code, out, _ = run("-c", str(bad), "scan", "x.test")
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("invalid JSON", out)

    def test_monitor_runs_cycles_and_stops(self):
        with LoopbackJava() as srv:
            code, out, _ = run("--db", self.db, "monitor", f"127.0.0.1:{srv.port}", "-e", "java",
                               "--cycles", "2", "-i", "5", "-t", "2")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out.count("-- cycle"), 2)
        self.assertIn("stopped after 2 cycle", out)

    def test_interrupt_mid_scan_finishes_and_saves_cycle(self):
        """Regression: Ctrl+C during a scan must not drop the in-flight cycle."""
        import signal
        import threading
        from minescope.database import Database
        with LoopbackJava(delay=1.0) as srv:
            timer = threading.Timer(0.4, lambda: signal.raise_signal(signal.SIGINT))
            timer.start()
            code, out, _ = run("--db", self.db, "monitor", f"127.0.0.1:{srv.port}", "-e", "java",
                               "-i", "5", "-t", "4", "--no-query")
            timer.join()
            with Database(self.db) as db:
                rows = db.history("127.0.0.1", srv.port)
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Stopping after the current cycle", out)
        self.assertIn("stopped after 1 cycle", out)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].online)

    def test_interactive_menu_flow(self):
        from unittest import mock
        answers = iter(["6", "", "1", "auto", "!!bad!!", "", "2", "", "0"])
        out = io.StringIO()
        with mock.patch("builtins.input", lambda prompt="": next(answers)), \
                contextlib.redirect_stdout(out):
            code = main(["--plain", "--db", self.db])
        text = out.getvalue()
        self.assertEqual(code, EXIT_OK)
        self.assertIn("TheYAZBAL", text)           # About page
        self.assertIn("Invalid host", text)         # validation error shown, menu keeps running
        self.assertIn("No servers configured", text)

    def test_report_without_data(self):
        code, out, _ = run("--db", self.db, "report", "html", "-o", self.reports)
        self.assertEqual(code, EXIT_OK)
        self.assertIn("No stored results", out)


if __name__ == "__main__":
    unittest.main()
