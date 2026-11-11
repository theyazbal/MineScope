import unittest

from minescope.models.server import Edition, ServerTarget
from minescope.scanner.batch import scan_many
from minescope.scanner.scanner import ServerScanner
from tests.fixtures.loopback import LoopbackJava, bedrock_server, closed_port, query_server


class LoopbackScanTests(unittest.TestCase):
    """Real sockets on 127.0.0.1 — no external network involved."""

    def test_java_over_real_tcp(self):
        with LoopbackJava() as srv:
            r = ServerScanner(timeout=2, try_query=False).scan(
                ServerTarget("127.0.0.1", srv.port, Edition.JAVA))
        self.assertTrue(r.online, r.error)
        self.assertEqual((r.version, r.players_online, r.player_names), ("Paper 1.21", 2, ["Alice", "Bob"]))
        self.assertEqual(r.motd, "Hello World")
        self.assertGreater(r.latency_ms, 0)

    def test_bedrock_over_real_udp(self):
        with bedrock_server() as srv:
            r = ServerScanner(timeout=2).scan(ServerTarget("127.0.0.1", srv.port, Edition.BEDROCK))
        self.assertTrue(r.online, r.error)
        self.assertEqual((r.edition, r.version, r.players_online, r.players_max), ("bedrock", "1.21.0", 3, 10))
        self.assertEqual(r.player_names, [])

    def test_query_over_real_udp(self):
        with LoopbackJava() as java, query_server() as q:
            r = ServerScanner(timeout=2).scan(
                ServerTarget("127.0.0.1", java.port, Edition.JAVA, query_port=q.port))
        self.assertTrue(r.query_available)
        self.assertEqual(r.player_names, ["Steve", "Alex"])
        self.assertEqual(r.plugins, ["WorldEdit 7.0", "Vault 1.7"])

    def test_auto_detection_both_editions(self):
        with LoopbackJava() as java:
            r = ServerScanner(timeout=1, try_query=False).scan(ServerTarget("127.0.0.1", java.port))
            self.assertEqual(r.edition, "java")
        with bedrock_server() as be:
            r = ServerScanner(timeout=1).scan(ServerTarget("127.0.0.1", be.port))
            self.assertEqual(r.edition, "bedrock")

    def test_refused_and_timeout(self):
        sc = ServerScanner(timeout=0.5, try_query=False)
        r = sc.scan(ServerTarget("127.0.0.1", closed_port(), Edition.JAVA))
        self.assertFalse(r.online)
        self.assertEqual(r.error, "Connection refused")
        r = sc.scan(ServerTarget("127.0.0.1", closed_port(), Edition.BEDROCK))
        self.assertFalse(r.online)  # nothing answers UDP -> timeout (or ICMP refusal)
        self.assertTrue(r.error)

    def test_many_concurrent(self):
        with LoopbackJava() as a, bedrock_server() as b:
            targets = [ServerTarget("127.0.0.1", a.port, Edition.JAVA, name="j"),
                       ServerTarget("127.0.0.1", b.port, Edition.BEDROCK, name="b"),
                       ServerTarget("127.0.0.1", closed_port(), Edition.JAVA, name="x")]
            sc = ServerScanner(timeout=1, try_query=False)
            res = scan_many(targets, sc.scan, 3)
        self.assertEqual([(r.name, r.online) for r in res], [("j", True), ("b", True), ("x", False)])


if __name__ == "__main__":
    unittest.main()
