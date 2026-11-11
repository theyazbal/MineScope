import unittest

from minescope.core.errors import ProtocolError, ServerTimeout
from minescope.protocols.java.query import JavaQueryClient, parse_challenge, parse_full_stat
from tests.fixtures.fakes import FakeUdpSocket, query_responder


class QueryTests(unittest.TestCase):
    def test_full_roundtrip(self):
        sock = FakeUdpSocket(query_responder())
        resp = JavaQueryClient(lambda h, p: sock).ping("h", 25565, 1)
        s = resp.snapshot
        self.assertEqual(s.player_names, ["Steve", "Alex"])
        self.assertEqual((s.players_online, s.players_max), (2, 20))
        self.assertEqual(s.software, "Paper on 1.21")
        self.assertEqual(s.plugins, ["WorldEdit 7.0", "Vault 1.7"])
        self.assertEqual(s.map_name, "world")
        self.assertEqual(len(sock.sent), 2)
        self.assertTrue(sock.closed)

    def test_no_players_gives_empty_list(self):
        sock = FakeUdpSocket(query_responder(names=()))
        s = JavaQueryClient(lambda h, p: sock).ping("h", 1, 1).snapshot
        self.assertEqual(s.player_names, [])

    def test_disabled_query_times_out(self):
        with self.assertRaises(ServerTimeout):
            JavaQueryClient(lambda h, p: FakeUdpSocket(query_responder(fail=True))).ping("h", 1, 1)

    def test_bad_responses(self):
        with self.assertRaises(ProtocolError):
            parse_challenge(b"\x09\x00\x00\x00\x01abc\x00", 1)
        with self.assertRaises(ProtocolError):
            parse_challenge(b"\x09\x00\x00\x00\x01", 1)
        with self.assertRaises(ProtocolError):
            parse_full_stat(b"\x00\x00\x00\x00\x01garbage", 1)


if __name__ == "__main__":
    unittest.main()
