import threading
import time
import unittest

from minescope.core.errors import ConnectionFailure
from minescope.models.server import Edition, ScanResult, ServerTarget
from minescope.protocols.base import PingResponse
from minescope.models.server import StatusSnapshot
from minescope.scanner.batch import scan_many
from minescope.scanner.scanner import ServerScanner


class StubClient:
    def __init__(self, snapshot=None, error=None, latency=5.0, delay=0.0):
        self.snapshot, self.error, self.latency, self.delay = snapshot, error, latency, delay
        self.calls = []

    def ping(self, host, port, timeout):
        self.calls.append((host, port))
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return PingResponse(self.snapshot, self.latency)


JAVA = StatusSnapshot(version="1.21", motd="J", players_online=1, players_max=10, player_names=["A"])
BE = StatusSnapshot(version="1.21.0", motd="B", players_online=0, players_max=5)
QUERY = StatusSnapshot(players_online=2, players_max=10, player_names=["A", "B"],
                       software="Paper", plugins=["X"], map_name="w", gamemode="SMP")


def target(edition, **kw):
    return ServerTarget("h.test", 25565, edition, **kw)


class ScannerTests(unittest.TestCase):
    def test_java_with_query_merge(self):
        sc = ServerScanner(java=StubClient(JAVA), bedrock=StubClient(error=AssertionError),
                           query=StubClient(QUERY))
        r = sc.scan(target(Edition.JAVA))
        self.assertTrue(r.online and r.query_available)
        self.assertEqual(r.player_names, ["A", "B"])
        self.assertEqual(r.players_online, 2)
        self.assertEqual(r.software, "Paper")

    def test_query_failure_is_silent(self):
        sc = ServerScanner(java=StubClient(JAVA), bedrock=StubClient(),
                           query=StubClient(error=ConnectionFailure("x")))
        r = sc.scan(target(Edition.JAVA))
        self.assertTrue(r.online)
        self.assertFalse(r.query_available)
        self.assertEqual(r.player_names, ["A"])

    def test_query_disabled(self):
        q = StubClient(QUERY)
        sc = ServerScanner(try_query=False, java=StubClient(JAVA), bedrock=StubClient(), query=q)
        sc.scan(target(Edition.JAVA))
        self.assertEqual(q.calls, [])

    def test_query_port_override(self):
        q = StubClient(QUERY)
        sc = ServerScanner(java=StubClient(JAVA), bedrock=StubClient(), query=q)
        sc.scan(target(Edition.JAVA, query_port=25575))
        self.assertEqual(q.calls, [("h.test", 25575)])

    def test_bedrock(self):
        sc = ServerScanner(java=StubClient(error=AssertionError), bedrock=StubClient(BE),
                           query=StubClient())
        r = sc.scan(target(Edition.BEDROCK))
        self.assertEqual((r.edition, r.online, r.player_names), ("bedrock", True, []))

    def test_offline_records_error_no_exception(self):
        sc = ServerScanner(java=StubClient(error=ConnectionFailure("Connection refused")),
                           bedrock=StubClient(), query=StubClient())
        r = sc.scan(target(Edition.JAVA))
        self.assertFalse(r.online)
        self.assertEqual(r.error, "Connection refused")
        self.assertIsNone(r.players_online)

    def test_unexpected_exception_is_contained(self):
        sc = ServerScanner(java=StubClient(error=ValueError("boom")), bedrock=StubClient(),
                           query=StubClient())
        self.assertIn("boom", sc.scan(target(Edition.JAVA)).error)

    def test_auto_detects_java(self):
        sc = ServerScanner(java=StubClient(JAVA), bedrock=StubClient(error=ConnectionFailure("t")),
                           query=StubClient(error=ConnectionFailure("t")))
        self.assertEqual(sc.scan(target(Edition.AUTO)).edition, "java")

    def test_auto_detects_bedrock(self):
        sc = ServerScanner(java=StubClient(error=ConnectionFailure("refused")), bedrock=StubClient(BE),
                           query=StubClient())
        self.assertEqual(sc.scan(target(Edition.AUTO)).edition, "bedrock")

    def test_auto_prefers_java_when_both_answer(self):
        sc = ServerScanner(java=StubClient(JAVA), bedrock=StubClient(BE), query=StubClient(error=ValueError()))
        self.assertEqual(sc.scan(target(Edition.AUTO)).edition, "java")

    def test_auto_both_fail(self):
        sc = ServerScanner(java=StubClient(error=ConnectionFailure("a")),
                           bedrock=StubClient(error=ConnectionFailure("b")), query=StubClient())
        r = sc.scan(target(Edition.AUTO))
        self.assertFalse(r.online)
        self.assertEqual(r.edition, "unknown")
        self.assertIn("Java (a)", r.error)
        self.assertIn("Bedrock (b)", r.error)


class BatchTests(unittest.TestCase):
    def make_targets(self, n):
        return [ServerTarget(f"h{i}.test", 1000 + i, Edition.JAVA) for i in range(n)]

    def test_order_and_completeness(self):
        res = scan_many(self.make_targets(12), lambda t: ScanResult(t.label, t.host, t.port, "java", True), 4)
        self.assertEqual([r.port for r in res], [1000 + i for i in range(12)])

    def test_concurrency_is_bounded_and_parallel(self):
        lock, state = threading.Lock(), {"now": 0, "peak": 0}

        def slow(t):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return ScanResult(t.label, t.host, t.port, "java", True)

        scan_many(self.make_targets(12), slow, 3)
        self.assertLessEqual(state["peak"], 3)
        self.assertGreater(state["peak"], 1)

    def test_parallel_is_faster_than_serial(self):
        def slow(t):
            time.sleep(0.05)
            return ScanResult(t.label, t.host, t.port, "java", True)
        start = time.perf_counter()
        scan_many(self.make_targets(8), slow, 8)
        self.assertLess(time.perf_counter() - start, 0.25)

    def test_stop_event_skips_pending(self):
        stop = threading.Event()

        def fn(t):
            stop.set()
            return ScanResult(t.label, t.host, t.port, "java", True)

        res = scan_many(self.make_targets(10), fn, 1, stop)
        self.assertEqual(len(res), 1)

    def test_empty_and_oversized_concurrency(self):
        self.assertEqual(scan_many([], lambda t: None, 99), [])


if __name__ == "__main__":
    unittest.main()
