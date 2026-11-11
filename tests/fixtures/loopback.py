"""Tiny real-socket Minecraft servers bound to 127.0.0.1 for integration tests."""

from __future__ import annotations

import socket
import threading
import time

from minescope.protocols.java.slp import read_packet
from tests.fixtures.fakes import (BEDROCK_ID, JAVA_DOC, bedrock_pong, java_status_response,
                                  query_responder)


class _Base:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self.sock.close()
        self.thread.join(2)


class LoopbackJava(_Base):
    def __init__(self, document=None, delay: float = 0.0) -> None:
        super().__init__()
        self.document = document or JAVA_DOC
        self.delay = delay
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(2)
        try:
            read_packet(conn)  # handshake
            read_packet(conn)  # status request
            if self.delay:
                time.sleep(self.delay)
            conn.sendall(java_status_response(self.document))
            pid, payload = read_packet(conn)  # ping
            from minescope.protocols.java.slp import build_packet
            conn.sendall(build_packet(pid, payload))
        except Exception:
            pass
        finally:
            conn.close()


class LoopbackUdp(_Base):
    def __init__(self, responder) -> None:
        super().__init__()
        self.responder = responder
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(2048)
            except (socket.timeout, OSError):
                continue
            reply = self.responder(data)
            for item in (reply if isinstance(reply, list) else [reply]):
                if item is not None:
                    self.sock.sendto(item, addr)


def bedrock_server() -> LoopbackUdp:
    return LoopbackUdp(lambda data: bedrock_pong(BEDROCK_ID) if data[:1] == b"\x01" else None)


def query_server() -> LoopbackUdp:
    return LoopbackUdp(query_responder())


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
