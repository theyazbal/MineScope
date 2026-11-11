"""Minecraft GameSpy4 / Query protocol (UDP full stat)."""

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

MAGIC = b"\xfe\xfd"
TYPE_HANDSHAKE = 9
TYPE_STAT = 0
_FULL_STAT_PADDING = b"\x00\x00\x00\x00"
_KV_HEADER = b"splitnum\x00\x80\x00"
_PLAYER_HEADER = b"\x01player_\x00\x00"


def session_id() -> int:
    """Return a random session id (only the low 4 bits of each byte are used)."""
    return random.getrandbits(32) & 0x0F0F0F0F


def build_handshake(sid: int) -> bytes:
    return MAGIC + bytes([TYPE_HANDSHAKE]) + struct.pack(">i", sid)


def build_full_stat(sid: int, token: int) -> bytes:
    return (MAGIC + bytes([TYPE_STAT]) + struct.pack(">i", sid)
            + struct.pack(">i", token) + _FULL_STAT_PADDING)


def parse_challenge(data: bytes, sid: int) -> int:
    """Extract the challenge token from a handshake response."""
    if len(data) < 6 or data[0] != TYPE_HANDSHAKE:
        raise ProtocolError("Invalid query handshake response")
    if struct.unpack(">i", data[1:5])[0] != sid:
        raise ProtocolError("Query session id mismatch")
    text = data[5:].split(b"\x00", 1)[0]
    try:
        return int(text.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError("Invalid query challenge token") from None


def parse_full_stat(data: bytes, sid: int) -> StatusSnapshot:
    """Parse a full stat response into a :class:`StatusSnapshot`."""
    if len(data) < 5 or data[0] != TYPE_STAT:
        raise ProtocolError("Invalid query stat response")
    if struct.unpack(">i", data[1:5])[0] != sid:
        raise ProtocolError("Query session id mismatch")
    body = data[5:]
    if not body.startswith(_KV_HEADER):
        raise ProtocolError("Unexpected query stat layout")
    body = body[len(_KV_HEADER):]
    split = body.find(_PLAYER_HEADER)
    if split == -1:
        raise ProtocolError("Query response has no player section")
    kv_block, player_block = body[:split], body[split + len(_PLAYER_HEADER):]
    parts = kv_block.split(b"\x00")
    pairs: dict[str, str] = {}
    for i in range(0, len(parts) - 1, 2):
        if not parts[i]:
            break
        pairs[parts[i].decode("utf-8", "replace")] = parts[i + 1].decode("utf-8", "replace")
    names = [n.decode("utf-8", "replace") for n in player_block.split(b"\x00") if n]
    plugins: list[str] = []
    software = None
    raw_plugins = pairs.get("plugins", "")
    if raw_plugins:
        head, _, rest = raw_plugins.partition(":")
        software = head.strip() or None
        plugins = [p.strip() for p in rest.split(";") if p.strip()]

    def to_int(key: str) -> int | None:
        try:
            return int(pairs[key])
        except (KeyError, ValueError):
            return None

    return StatusSnapshot(
        version=pairs.get("version"),
        motd=pairs.get("hostname"),
        players_online=to_int("numplayers"),
        players_max=to_int("maxplayers"),
        player_names=names,
        gamemode=pairs.get("gametype"),
        map_name=pairs.get("map"),
        software=software,
        plugins=plugins,
        extra={"raw": pairs},
    )


class JavaQueryClient(ProtocolClient):
    """Java Query client. Only works where ``enable-query=true`` is set."""

    edition = "java-query"

    def __init__(self, udp_factory: UdpFactory = default_udp_factory) -> None:
        self._factory = udp_factory

    def ping(self, host: str, port: int, timeout: float) -> PingResponse:
        sock: DatagramSocket = self._factory(host, port)
        try:
            sock.settimeout(timeout)
            sid = session_id()
            started = time.perf_counter()
            sock.sendto(build_handshake(sid), (host, port))
            token = parse_challenge(recv_datagram(sock), sid)
            sock.sendto(build_full_stat(sid, token), (host, port))
            snapshot = parse_full_stat(recv_datagram(sock), sid)
            latency = (time.perf_counter() - started) * 1000
            return PingResponse(snapshot=snapshot, latency_ms=round(latency, 2))
        finally:
            sock.close()
