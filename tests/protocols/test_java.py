import json
import socket
import struct
import unittest

from minescope.core.errors import ConnectionFailure, ProtocolError, ServerTimeout
from minescope.protocols.java.motd import flatten_component, strip_formatting
from minescope.protocols.java.slp import JavaPingClient, build_handshake, parse_status
from minescope.protocols.java.varint import decode_varint, encode_string, encode_varint
from tests.fixtures.fakes import JAVA_DOC, FakeStreamSocket, java_status_response


class VarIntTests(unittest.TestCase):
    def test_roundtrip(self):
        for value in (0, 1, 127, 128, 255, 25565, 2097151, 2147483647, -1, -2147483648):
            self.assertEqual(decode_varint(encode_varint(value))[0], value)

    def test_known_encodings(self):
        self.assertEqual(encode_varint(300), b"\xac\x02")
        self.assertEqual(encode_varint(-1), b"\xff\xff\xff\xff\x0f")

    def test_too_long_and_truncated(self):
        with self.assertRaises(ProtocolError):
            decode_varint(b"\x80\x80\x80\x80\x80\x01")
        with self.assertRaises(ProtocolError):
            decode_varint(b"\x80")

    def test_string(self):
        self.assertEqual(encode_string("hi"), b"\x02hi")


class MotdTests(unittest.TestCase):
    def test_strip_codes(self):
        self.assertEqual(strip_formatting("§aGreen§r text"), "Green text")

    def test_components(self):
        self.assertEqual(flatten_component({"text": "A", "extra": [{"text": "B"}, "C"]}), "ABC")
        self.assertEqual(flatten_component(["x", {"text": "y"}]), "xy")
        self.assertEqual(flatten_component(None), "")

    def test_depth_limit(self):
        deep: dict = {"text": "x"}
        for _ in range(100):
            deep = {"text": "", "extra": [deep]}
        flatten_component(deep)  # must not recurse forever


class JavaPingTests(unittest.TestCase):
    def client(self, sock):
        return JavaPingClient(lambda host, port, timeout: sock)

    def test_successful_ping(self):
        sock = FakeStreamSocket(java_status_response(JAVA_DOC))
        resp = self.client(sock).ping("example.test", 25565, 2)
        s = resp.snapshot
        self.assertEqual((s.version, s.protocol), ("Paper 1.21", 767))
        self.assertEqual(s.motd, "Hello World")
        self.assertEqual((s.players_online, s.players_max), (2, 20))
        self.assertEqual(s.player_names, ["Alice", "Bob"])
        self.assertGreaterEqual(resp.latency_ms, 0)
        self.assertTrue(sock.closed)

    def test_handshake_bytes(self):
        sent = build_handshake("a.b", 25565)
        # length, id 0, protocol -1, host, port, next state 1
        self.assertEqual(sent[1], 0)
        self.assertTrue(sent.endswith(struct.pack(">H", 25565) + b"\x01"))
        sock = FakeStreamSocket(java_status_response(JAVA_DOC))
        self.client(sock).ping("a.b", 25565, 2)
        self.assertEqual(sock.sent[0], sent)
        self.assertEqual(sock.sent[1], b"\x01\x00")

    def test_status_valid_without_pong(self):
        sock = FakeStreamSocket(java_status_response(JAVA_DOC), pong=False)
        resp = self.client(sock).ping("h", 1, 1)
        self.assertEqual(resp.snapshot.players_online, 2)

    def test_missing_fields_are_none_not_invented(self):
        sock = FakeStreamSocket(java_status_response({"description": "x"}))
        s = self.client(sock).ping("h", 1, 1).snapshot
        self.assertIsNone(s.version)
        self.assertIsNone(s.players_online)
        self.assertEqual(s.player_names, [])

    def test_malformed_json(self):
        bad = encode_varint(0) + encode_string("{not json")
        with self.assertRaises(ProtocolError):
            parse_status(encode_string("{not json"))
        sock = FakeStreamSocket(encode_varint(len(bad)) + bad)
        with self.assertRaises(ProtocolError):
            self.client(sock).ping("h", 1, 1)
        self.assertTrue(sock.closed)

    def test_json_not_object(self):
        with self.assertRaises(ProtocolError):
            parse_status(encode_string(json.dumps([1, 2])))

    def test_wrong_packet_id(self):
        payload = encode_varint(5) + encode_string("{}")
        sock = FakeStreamSocket(encode_varint(len(payload)) + payload)
        with self.assertRaises(ProtocolError):
            self.client(sock).ping("h", 1, 1)

    def test_oversized_length_rejected(self):
        sock = FakeStreamSocket(encode_varint(50_000_000))
        with self.assertRaises(ProtocolError):
            self.client(sock).ping("h", 1, 1)

    def test_truncated_response(self):
        data = java_status_response(JAVA_DOC)[:10]
        with self.assertRaises(ProtocolError):
            self.client(FakeStreamSocket(data)).ping("h", 1, 1)

    def test_timeout_and_os_errors(self):
        with self.assertRaises(ServerTimeout):
            self.client(FakeStreamSocket(raise_on_recv=socket.timeout())).ping("h", 1, 1)
        with self.assertRaises(ConnectionFailure):
            self.client(FakeStreamSocket(raise_on_recv=ConnectionResetError(104, "reset"))).ping("h", 1, 1)

    def test_connector_failure_propagates(self):
        def refuse(host, port, timeout):
            raise ConnectionFailure("Connection refused")
        with self.assertRaises(ConnectionFailure):
            JavaPingClient(refuse).ping("h", 1, 1)


if __name__ == "__main__":
    unittest.main()
