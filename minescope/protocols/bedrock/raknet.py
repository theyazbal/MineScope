"""Bedrock RakNet Unconnected Ping / Pong."""

from __future__ import annotations

import random
import struct
import time

from minescope.core.errors import ProtocolError
from minescope.models.server import StatusSnapshot
from minescope.protocols.base import (
    DatagramSocket,
    PingResponse,
    ProtocolClient,
    UdpFactory,
    default_udp_factory,
    recv_datagram,
)

OFFLINE_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")
ID_UNCONNECTED_PING = 0x01
ID_UNCONNECTED_PONG = 0x1C


def build_unconnected_ping(timestamp_ms: int, client_guid: int) -> bytes:
    """Build an Unconnected Ping datagram."""
    return (bytes([ID_UNCONNECTED_PING]) + struct.pack(">q", timestamp_ms)
            + OFFLINE_MAGIC + struct.pack(">q", client_guid))


def parse_pong(data: bytes) -> StatusSnapshot:
    """Parse an Unconnected Pong datagram."""
    header = 1 + 8 + 8 + 16 + 2
    if len(data) < header or data[0] != ID_UNCONNECTED_PONG:
        raise ProtocolError("Not a RakNet Unconnected Pong")
    if data[17:33] != OFFLINE_MAGIC:
        raise ProtocolError("RakNet magic mismatch")
    server_guid = struct.unpack(">q", data[9:17])[0]
    (length,) = struct.unpack(">H", data[33:35])
    raw = data[35:35 + length]
    if len(raw) != length:
        raise ProtocolError("Pong payload is truncated")
    return parse_server_id_string(raw.decode("utf-8", "replace"), server_guid)


def _int(fields: list[str], index: int) -> int | None:
    try:
        return int(fields[index])
    except (IndexError, ValueError):
        return None


def parse_server_id_string(text: str, server_guid: int | None = None) -> StatusSnapshot:
    """Parse the semicolon separated Bedrock server id string."""
    fields = text.split(";")
    if len(fields) < 6 or fields[0] not in ("MCPE", "MCEE"):
        raise ProtocolError("Unrecognized Bedrock server id string")
    motd = fields[1]
    extra: dict[str, object] = {"edition_tag": fields[0]}
    if server_guid is not None:
        extra["guid"] = server_guid
    if _int(fields, 10) is not None:
        extra["port_v4"] = _int(fields, 10)
    if _int(fields, 11) is not None:
        extra["port_v6"] = _int(fields, 11)
    return StatusSnapshot(
        version=fields[3] or None,
        protocol=_int(fields, 2),
        motd=motd or None,
        players_online=_int(fields, 4),
        players_max=_int(fields, 5),
        server_id=fields[6] if len(fields) > 6 and fields[6] else None,
        map_name=fields[7] if len(fields) > 7 and fields[7] else None,
        gamemode=fields[8] if len(fields) > 8 and fields[8] else None,
        extra=extra,
    )


class BedrockPingClient(ProtocolClient):
    """Bedrock Edition status client. Does not expose player names (protocol limit)."""

    edition = "bedrock"

    def __init__(self, udp_factory: UdpFactory = default_udp_factory) -> None:
        self._factory = udp_factory

    def ping(self, host: str, port: int, timeout: float) -> PingResponse:
        sock: DatagramSocket = self._factory(host, port)
        try:
            sock.settimeout(timeout)
            guid = random.getrandbits(63)
            started = time.perf_counter()
            sock.sendto(build_unconnected_ping(int(time.time() * 1000), guid), (host, port))
            data = recv_datagram(sock)
            latency = (time.perf_counter() - started) * 1000
            return PingResponse(snapshot=parse_pong(data), latency_ms=round(latency, 2))
        finally:
            sock.close()
