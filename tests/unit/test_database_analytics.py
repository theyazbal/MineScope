import os
import sqlite3
import tempfile
import unittest

from minescope.core.errors import ValidationError
from minescope.database import Database
from minescope.database.migrations import MIGRATIONS
from minescope.models.server import ScanResult
from minescope.services.analytics import compute_statistics, parse_since


def res(online, i, host="h.test", port=25565, **kw):
    return ScanResult(name="srv", host=host, port=port, edition="java", online=online,
                      latency_ms=kw.pop("latency_ms", 10.0 + i if online else None),
                      players_online=kw.pop("players", i if online else None), players_max=20 if online else None,
                      scanned_at=f"2026-01-{i + 1:02d}T00:00:00+00:00", **kw)


class DatabaseTests(unittest.TestCase):
    def test_schema_version_and_file_persistence(self):
        path = os.path.join(tempfile.mkdtemp(), "nested", "m.db")
        with Database(path) as db:
            self.assertEqual(db.schema_version, len(MIGRATIONS))
            db.save_result(res(True, 0, player_names=["Ünï", "B"]))
        with Database(path) as db:  # reopen: no re-migration, data present
            self.assertEqual(db.schema_version, len(MIGRATIONS))
            rec = db.history("h.test", 25565)
            self.assertEqual(len(rec), 1)
            self.assertEqual(rec[0].player_names, ["Ünï", "B"])
            self.assertTrue(rec[0].online)

    def test_history_order_limit_since(self):
        with Database() as db:
            for i in (2, 0, 1, 3):
                db.save_result(res(True, i))
            self.assertEqual([r.scanned_at[8:10] for r in db.history("h.test", 25565)], ["01", "02", "03", "04"])
            last2 = db.history("h.test", 25565, limit=2)
            self.assertEqual([r.scanned_at[8:10] for r in last2], ["03", "04"])
            self.assertEqual(len(db.history("h.test", 25565, since="2026-01-03T00:00:00+00:00")), 2)
            self.assertEqual(db.history("nope.test", 1), [])

    def test_servers_latest_and_upsert(self):
        with Database() as db:
            db.save_result(res(True, 0))
            db.save_result(res(False, 1))
            db.save_result(res(True, 0, host="other.test", port=1))
            self.assertEqual(len(db.servers()), 2)
            latest = {r.host: r for r in db.latest()}
            self.assertFalse(latest["h.test"].online)
            self.assertTrue(latest["other.test"].online)

    def test_sql_injection_is_inert(self):
        with Database() as db:
            evil = "x'); DROP TABLE scans;--"
            db.save_result(res(True, 0, host="h.test", motd=evil, error=evil))
            self.assertEqual(db.history("h.test'; DROP TABLE servers;--", 1), [])
            self.assertEqual(db.history("h.test", 25565)[0].motd, evil)

    def test_purge(self):
        with Database() as db:
            for i in range(4):
                db.save_result(res(True, i))
            self.assertEqual(db.purge_before("2026-01-03T00:00:00+00:00"), 2)
            self.assertEqual(len(db.history("h.test", 25565)), 2)

    def test_concurrent_writes(self):
        import threading
        with Database() as db:
            threads = [threading.Thread(target=lambda n=n: [db.save_result(res(True, n % 20)) for _ in range(20)])
                       for n in range(6)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(len(db.history("h.test", 25565)), 120)

    def test_opens_existing_empty_database_file(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(path)
        conn.close()
        with Database(path) as db:
            self.assertEqual(db.schema_version, len(MIGRATIONS))


class AnalyticsTests(unittest.TestCase):
    def test_statistics(self):
        with Database() as db:
            for i, on in enumerate([True, False, False, True, True, False]):
                db.save_result(res(on, i))
            s = compute_statistics(db.history("h.test", 25565))
        self.assertEqual((s.checks, s.online_checks, s.uptime_percent), (6, 3, 50.0))
        self.assertEqual((s.outages, s.longest_outage_checks), (2, 2))
        self.assertEqual((s.latency_min_ms, s.latency_max_ms), (10.0, 14.0))
        self.assertEqual(s.latency_avg_ms, 12.33)
        self.assertEqual(s.players_peak, 4)
        self.assertEqual(s.last_online, "2026-01-05T00:00:00+00:00")

    def test_empty_and_all_offline(self):
        s = compute_statistics([])
        self.assertEqual((s.checks, s.uptime_percent, s.latency_avg_ms, s.players_peak), (0, None, None, None))
        with Database() as db:
            db.save_result(res(False, 0))
            s = compute_statistics(db.history("h.test", 25565))
        self.assertEqual((s.uptime_percent, s.last_online, s.outages), (0.0, None, 1))

    def test_parse_since(self):
        self.assertRegex(parse_since("24h"), r"^\d{4}-\d\d-\d\dT")
        self.assertTrue(parse_since("2026-01-01").startswith("2026-01-01T00:00:00"))
        for bad in ("", "abc", "h", "-5d", "1x"):
            with self.assertRaises(ValidationError, msg=bad):
                parse_since(bad)


if __name__ == "__main__":
    unittest.main()
