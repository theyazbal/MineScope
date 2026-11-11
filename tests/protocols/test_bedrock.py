import unittest

from minescope.core.errors import ProtocolError, ServerTimeout
from minescope.protocols.bedrock.raknet import (
    OFFLINE_MAGIC, BedrockPingClient, build_unconnected_ping, parse_pong, parse_server_id_string)
from tests.fixtures.fakes import BEDROCK_ID, FakeUdpSocket, bedrock_pong


class BedrockTests(unittest.TestCase):
    def test_ping_packet_layout(self):
        pkt = build_unconnected_ping(1, 2)
        self.assertEqual(len(pkt), 33)
        self.assertEqual(pkt[0], 0x01)
        self.assertEqual(pkt[9:25], OFFLINE_MAGIC)

    def test_parse_pong(self):
        s = parse_pong(bedrock_pong(BEDROCK_ID))
        self.assertEqual((s.motd, s.protocol, s.version), ("My Bedrock", 712, "1.21.0"))
        self.assertEqual((s.players_online, s.players_max), (3, 10))
        self.assertEqual((s.map_name, s.gamemode, s.server_id), ("World", "Survival", "1234567890"))
        self.assertEqual(s.player_names, [])  # protocol never exposes names
        self.assertEqual(s.extra["port_v4"], 19132)

    def test_short_id_string_still_parses(self):
        s = parse_server_id_string("MCPE;Hi;1;1.0;0;5;99")
        self.assertEqual((s.players_online, s.players_max), (0, 5))
        self.assertIsNone(s.gamemode)

    def test_invalid_inputs(self):
        for bad in (b"", b"\x1c" + b"\x00" * 10, bedrock_pong("HTTP;x"), bedrock_pong("MCPE;a;b")):
            with self.assertRaises(ProtocolError):
                parse_pong(bad)
        broken = bytearray(bedrock_pong(BEDROCK_ID))
        broken[20] ^= 0xFF  # corrupt magic
        with self.assertRaises(ProtocolError):
            parse_pong(bytes(broken))
        with self.assertRaises(ProtocolError):
            parse_pong(bedrock_pong(BEDROCK_ID)[:-5])  # truncated payload

    def test_client_roundtrip_and_cleanup(self):
        sock = FakeUdpSocket(lambda data: bedrock_pong(BEDROCK_ID))
        resp = BedrockPingClient(lambda h, p: sock).ping("h", 19132, 1)
        self.assertEqual(resp.snapshot.players_online, 3)
        self.assertEqual(sock.sent[0][0], 0x01)
        self.assertTrue(sock.closed)

    def test_timeout(self):
        sock = FakeUdpSocket(lambda data: None)
        with self.assertRaises(ServerTimeout):
            BedrockPingClient(lambda h, p: sock).ping("h", 19132, 1)
        self.assertTrue(sock.closed)


if __name__ == "__main__":
    unittest.main()
