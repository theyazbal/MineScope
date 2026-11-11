"""Single-target scanning with automatic edition detection."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from minescope.core.errors import describe_error
from minescope.models.server import Edition, ScanResult, ServerTarget
from minescope.protocols.base import PingResponse, ProtocolClient
from minescope.protocols.bedrock import BedrockPingClient
from minescope.protocols.java import JavaPingClient, JavaQueryClient

log = logging.getLogger(__name__)

QUERY_TIMEOUT_CAP = 1.0  # most servers have Query disabled; don't make them wait long


class _QueryJob:
    """Result holder for a background Query attempt."""

    def __init__(self) -> None:
        self.response: Optional[PingResponse] = None
        self.done = threading.Event()


class ServerScanner:
    """Scan one :class:`ServerTarget` using the appropriate protocol(s)."""

    def __init__(self, timeout: float = 3.0, try_query: bool = True,
                 java: Optional[ProtocolClient] = None,
                 bedrock: Optional[ProtocolClient] = None,
                 query: Optional[ProtocolClient] = None) -> None:
        self.timeout = timeout
        self.try_query = try_query
        self._java = java or JavaPingClient()
        self._bedrock = bedrock or BedrockPingClient()
        self._query = query or JavaQueryClient()

    def scan(self, target: ServerTarget) -> ScanResult:
        """Scan ``target``. Never raises for network problems."""
        if target.edition is Edition.JAVA:
            return self._scan_java(target)
        if target.edition is Edition.BEDROCK:
            return self._scan_bedrock(target)
        return self._scan_auto(target)

    # -- edition specific -------------------------------------------------
    def _base(self, target: ServerTarget, edition: str) -> ScanResult:
        return ScanResult(name=target.label, host=target.host, port=target.port,
                          edition=edition, online=False)

    def _fill(self, result: ScanResult, response: PingResponse) -> ScanResult:
        snap = response.snapshot
        result.online = True
        result.latency_ms = response.latency_ms
        result.version = snap.version
        result.protocol = snap.protocol
        result.motd = snap.motd
        result.players_online = snap.players_online
        result.players_max = snap.players_max
        result.player_names = list(snap.player_names)
        result.gamemode = snap.gamemode
        result.map_name = snap.map_name
        result.software = snap.software
        result.plugins = list(snap.plugins)
        return result

    def _scan_java(self, target: ServerTarget) -> ScanResult:
        result = self._base(target, "java")
        query_job = self._start_query(target) if self.try_query else None
        try:
            response = self._java.ping(target.host, target.port, self.timeout)
        except Exception as exc:  # noqa: BLE001 - boundary: convert to result
            result.error = describe_error(exc)
            log.debug("java scan failed for %s: %s", target.address, result.error)
            return result
        self._fill(result, response)
        if query_job is not None:
            self._merge_query(result, query_job)
        return result

    def _start_query(self, target: ServerTarget) -> "_QueryJob":
        """Run the optional Query in the background, concurrently with the status ping."""
        job = _QueryJob()
        port = target.query_port or target.port
        timeout = min(self.timeout, QUERY_TIMEOUT_CAP)

        def work() -> None:
            try:
                job.response = self._query.ping(target.host, port, timeout)
            except Exception as exc:  # noqa: BLE001 - query is optional
                log.debug("query unavailable for %s: %s", target.address, describe_error(exc))
            finally:
                job.done.set()

        threading.Thread(target=work, name="minescope-query", daemon=True).start()
        return job

    def _merge_query(self, result: ScanResult, job: "_QueryJob") -> None:
        job.done.wait(QUERY_TIMEOUT_CAP + self.timeout)
        if job.response is None:
            return
        snap = job.response.snapshot
        result.query_available = True
        if snap.player_names:
            result.player_names = list(snap.player_names)
        if snap.players_online is not None:
            result.players_online = snap.players_online
        if snap.players_max is not None:
            result.players_max = snap.players_max
        result.software = snap.software or result.software
        result.plugins = list(snap.plugins)
        result.map_name = snap.map_name or result.map_name
        result.gamemode = snap.gamemode or result.gamemode

    def _scan_bedrock(self, target: ServerTarget) -> ScanResult:
        result = self._base(target, "bedrock")
        try:
            response = self._bedrock.ping(target.host, target.port, self.timeout)
        except Exception as exc:  # noqa: BLE001
            result.error = describe_error(exc)
            log.debug("bedrock scan failed for %s: %s", target.address, result.error)
            return result
        return self._fill(result, response)

    def _scan_auto(self, target: ServerTarget) -> ScanResult:
        """Probe both editions in parallel. Java wins if both answer."""
        with ThreadPoolExecutor(max_workers=2) as pool:
            java_future = pool.submit(self._scan_java, target)
            bedrock_future = pool.submit(self._scan_bedrock, target)
            java_result = java_future.result()
            bedrock_result = bedrock_future.result()
        if java_result.online:
            return java_result
        if bedrock_result.online:
            return bedrock_result
        result = self._base(target, "unknown")
        result.error = (f"No response as Java ({java_result.error}) "
                        f"or Bedrock ({bedrock_result.error})")
        return result
