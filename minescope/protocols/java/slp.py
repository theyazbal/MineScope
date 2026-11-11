"""Minecraft Java Edition Server List Ping (status protocol)."""

from __future__ import annotations

import json
import struct
import time
from typing import Any

from minescope.core.errors import ProtocolError
from minescope.models.server import StatusSnapshot
from minescope.protocols.base import (
    PingResponse,
    ProtocolClient,
    StreamSocket,
    TcpConnector,
    default_tcp_connector,
    recv_exact,
)
from minescope.protocols.java.motd import flatten_component, strip_formatting
from minescope.protocols.java.varint import decode_varint, encode_string, encode_varint, read_varint

PROTOCOL_VERSION = -1  # "unknown" is accepted by status requests
MAX_PACKET = 1 << 20  # 1 MiB safety cap (favicons make status packets large)


def build_packet(packet_id: int, payload: bytes = b"") -> bytes:
    """Frame ``payload`` with a packet id and length prefix."""
    body = encode_varint(packet_id) + payload
    return encode_varint(len(body)) + body


def build_handshake(host: str, port: int) -> bytes:
    """Build the handshake packet requesting the *status* state."""
    payload = (encode_varint(PROTOCOL_VERSION) + encode_string(host)
               + struct.pack(">H", port) + encode_varint(1))
    return build_packet(0x00, payload)


def read_packet(sock: StreamSocket) -> tuple[int, bytes]:
    """Read one framed packet and return ``(packet_id, payload)``."""
    length = read_varint(lambda: recv_exact(sock, 1)[0])
    if length <= 0 or length > MAX_PACKET:
        raise ProtocolError(f"Invalid packet length: {length}")
    body = recv_exact(sock, length)
    position = 0

    def next_byte() -> int:
        nonlocal position
        if position >= len(body):
            raise ProtocolError("Truncated packet")
        position += 1
        return body[position - 1]

    packet_id = read_varint(next_byte)
    return packet_id, body[position:]


def parse_status(payload: bytes) -> StatusSnapshot:
    """Parse the JSON status payload of a status response packet."""
    try:
        size, offset = decode_varint(payload)
        raw = payload[offset:offset + size]
        if size < 0 or len(raw) != size:
            raise ProtocolError("Status string is truncated")
        document: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Malformed status JSON: {exc}") from None
    if not isinstance(document, dict):
        raise ProtocolError("Status JSON is not an object")
    return snapshot_from_document(document)


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def snapshot_from_document(document: dict[str, Any]) -> StatusSnapshot:
    """Convert a status JSON document to a :class:`StatusSnapshot`."""
    version = document.get("version") if isinstance(document.get("version"), dict) else {}
    players = document.get("players") if isinstance(document.get("players"), dict) else {}
    names: list[str] = []
    sample = players.get("sample")
    if isinstance(sample, list):
        for entry in sample:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                name = strip_formatting(entry["name"]).strip()
                # Some servers use the sample for custom text; keep only plausible names.
                if name:
                    names.append(name)
    version_name = version.get("name")
    return StatusSnapshot(
        version=strip_formatting(version_name) if isinstance(version_name, str) else None,
        protocol=_as_int(version.get("protocol")),
        motd=flatten_component(document.get("description")).strip() or None,
        players_online=_as_int(players.get("online")),
        players_max=_as_int(players.get("max")),
        player_names=names,
        extra={"has_favicon": "favicon" in document,
               "enforces_secure_chat": document.get("enforcesSecureChat")},
    )


class JavaPingClient(ProtocolClient):
    """Java Edition Server List Ping client."""

    edition = "java"

    def __init__(self, connector: TcpConnector = default_tcp_connector) -> None:
        self._connector = connector

    def ping(self, host: str, port: int, timeout: float) -> PingResponse:
        sock = self._connector(host, port, timeout)
        try:
            sock.settimeout(timeout)
            sock.sendall(build_handshake(host, port))
            started = time.perf_counter()
            sock.sendall(build_packet(0x00))
            packet_id, payload = read_packet(sock)
            status_rtt = (time.perf_counter() - started) * 1000
            if packet_id != 0x00:
                raise ProtocolError(f"Unexpected packet id 0x{packet_id:02x}")
            snapshot = parse_status(payload)
            latency = status_rtt
            try:
                token = int(time.time() * 1000) & 0x7FFFFFFFFFFFFFFF
                ping_started = time.perf_counter()
                sock.sendall(build_packet(0x01, struct.pack(">q", token)))
                pong_id, pong = read_packet(sock)
                if pong_id == 0x01 and pong == struct.pack(">q", token):
                    latency = (time.perf_counter() - ping_started) * 1000
            except Exception:
                # Latency falls back to the status round trip; status is still valid.
                pass
            return PingResponse(snapshot=snapshot, latency_ms=round(latency, 2))
        finally:
            try:
                sock.close()
            except OSError:
                pass
