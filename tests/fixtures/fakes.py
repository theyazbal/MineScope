"""Offline test doubles: fake sockets and wire-format builders."""

from __future__ import annotations

import json
import socket
import struct
from typing import Callable, Optional

from minescope.protocols.bedrock.raknet import OFFLINE_MAGIC
from minescope.protocols.java.varint import encode_string, encode_varint


class FakeStreamSocket:
    """TCP socket stub that serves scripted bytes and records what was sent."""

    def __init__(self, response: bytes = b"", chunk: int = 7, raise_on_recv: Optional[BaseException] = None,
                 pong: bool = True) -> None:
        self.sent: list[bytes] = []
        self._buffer = bytearray(response)
        self._chunk = chunk
        self._raise = raise_on_recv
        self.closed = False
        self.timeout: float | None = None
        self._echo_pong = pong

    def settimeout(self, value): self.timeout = value

    def sendall(self, data: bytes) -> None:
        self.sent.append(bytes(data))
        # Echo a pong when a ping packet (id 0x01, 8 byte payload) is sent.
        if self._echo_pong and data[:2] == b"\x09\x01":
            self._buffer += data

    def recv(self, size: int) -> bytes:
        if self._raise:
            raise self._raise
        if not self._buffer:
            return b""
        take = min(size, self._chunk, len(self._buffer))
        out = bytes(self._buffer[:take])
        del self._buffer[:take]
        return out

    def close(self) -> None: self.closed = True


class FakeUdpSocket:
    """UDP socket stub; ``responder`` maps each sent datagram to a reply (or None)."""

    def __init__(self, responder: Callable[[bytes], Optional[bytes] | list[bytes]],
                 timeout_on_empty: bool = True) -> None:
        self._responder = responder
        self._queue: list[bytes] = []
        self.sent: list[bytes] = []
        self.closed = False
        self._timeout_on_empty = timeout_on_empty

    def settimeout(self, value): pass

    def sendto(self, data: bytes, address) -> int:
        self.sent.append(data)
        reply = self._responder(data)
        if isinstance(reply, list):
            self._queue.extend(reply)
        elif reply is not None:
            self._queue.append(reply)
        return len(data)

    def recvfrom(self, size: int):
        if not self._queue:
            raise socket.timeout("timed out")
        return self._queue.pop(0), ("127.0.0.1", 0)

    def close(self) -> None: self.closed = True


def java_status_response(document: dict) -> bytes:
    payload = encode_varint(0) + encode_string(json.dumps(document))
    return encode_varint(len(payload)) + payload


JAVA_DOC = {
    "version": {"name": "Paper 1.21", "protocol": 767},
    "players": {"max": 20, "online": 2, "sample": [{"name": "Alice", "id": "x"}, {"name": "Bob", "id": "y"}]},
    "description": {"text": "Hello ", "extra": [{"text": "World"}]},
}


def bedrock_pong(id_string: str, guid: int = 1234) -> bytes:
    raw = id_string.encode()
    return (b"\x1c" + struct.pack(">q", 0) + struct.pack(">q", guid) + OFFLINE_MAGIC
            + struct.pack(">H", len(raw)) + raw)


BEDROCK_ID = "MCPE;My Bedrock;712;1.21.0;3;10;1234567890;World;Survival;1;19132;19133;"


def query_responder(names=("Steve", "Alex"), fail: bool = False):
    """Return a responder emulating a Query-enabled server."""
    def respond(data: bytes):
        if fail:
            return None
        if data[2] == 9:
            return b"\x09" + data[3:7] + b"9513307\x00"
        sid = data[3:7]
        kv = (b"hostname\x00Query MOTD\x00gametype\x00SMP\x00version\x001.21\x00"
              b"plugins\x00Paper on 1.21: WorldEdit 7.0; Vault 1.7\x00map\x00world\x00"
              b"numplayers\x002\x00maxplayers\x0020\x00hostport\x0025565\x00\x00")
        players = b"".join(n.encode() + b"\x00" for n in names) + b"\x00"
        return (b"\x00" + sid + b"splitnum\x00\x80\x00" + kv + b"\x01player_\x00\x00" + players)
    return respond
