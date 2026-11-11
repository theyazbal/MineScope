"""Shared protocol abstractions and socket helpers."""

from __future__ import annotations

import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Protocol

from minescope.core.errors import ConnectionFailure, ProtocolError, ServerTimeout
from minescope.models.server import StatusSnapshot


class StreamSocket(Protocol):
    """Subset of a TCP socket used by the Java client."""

    def sendall(self, data: bytes) -> None: ...
    def recv(self, size: int) -> bytes: ...
    def settimeout(self, value: float | None) -> None: ...
    def close(self) -> None: ...


class DatagramSocket(Protocol):
    """Subset of a UDP socket used by Bedrock and Query clients."""

    def sendto(self, data: bytes, address: tuple[str, int]) -> int: ...
    def recvfrom(self, size: int) -> tuple[bytes, tuple]: ...
    def settimeout(self, value: float | None) -> None: ...
    def close(self) -> None: ...


TcpConnector = Callable[[str, int, float], StreamSocket]
UdpFactory = Callable[[str, int], DatagramSocket]


def default_tcp_connector(host: str, port: int, timeout: float) -> StreamSocket:
    """Open a TCP connection, translating errors to MineScope errors."""
    try:
        return socket.create_connection((host, port), timeout=timeout)  # type: ignore[return-value]
    except socket.timeout:
        raise ServerTimeout("Connection timed out") from None
    except socket.gaierror:
        raise ConnectionFailure("Host name could not be resolved") from None
    except ConnectionRefusedError:
        raise ConnectionFailure("Connection refused") from None
    except OSError as exc:
        raise ConnectionFailure(f"Network error: {exc.strerror or exc}") from None


class _ResolvedUdpSocket:
    """UDP socket bound to the first resolved address of the target."""

    def __init__(self, family: int, address: tuple) -> None:
        self._sock = socket.socket(family, socket.SOCK_DGRAM)
        self._address = address

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        return self._sock.sendto(data, self._address)

    def recvfrom(self, size: int) -> tuple[bytes, tuple]:
        return self._sock.recvfrom(size)

    def settimeout(self, value: float | None) -> None:
        self._sock.settimeout(value)

    def close(self) -> None:
        self._sock.close()


def default_udp_factory(host: str, port: int) -> DatagramSocket:
    """Create a UDP socket matching the address family of ``host``."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror:
        raise ConnectionFailure("Host name could not be resolved") from None
    family, _, _, _, address = infos[0]
    return _ResolvedUdpSocket(family, address)


def recv_exact(sock: StreamSocket, size: int) -> bytes:
    """Read exactly ``size`` bytes or raise a MineScope error."""
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except socket.timeout:
            raise ServerTimeout("Timed out waiting for server response") from None
        except OSError as exc:
            raise ConnectionFailure(f"Network error: {exc.strerror or exc}") from None
        if not chunk:
            raise ProtocolError("Connection closed before the response was complete")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_datagram(sock: DatagramSocket, size: int = 65535) -> bytes:
    """Receive one datagram or raise a MineScope error."""
    try:
        data, _ = sock.recvfrom(size)
    except socket.timeout:
        raise ServerTimeout("Timed out waiting for server response") from None
    except OSError as exc:
        raise ConnectionFailure(f"Network error: {exc.strerror or exc}") from None
    return data


@dataclass
class PingResponse:
    """Status snapshot plus measured round trip latency."""

    snapshot: StatusSnapshot
    latency_ms: float


class ProtocolClient(ABC):
    """Interface implemented by every status protocol client."""

    edition: str

    @abstractmethod
    def ping(self, host: str, port: int, timeout: float) -> PingResponse:
        """Query ``host:port`` and return a :class:`PingResponse`."""
