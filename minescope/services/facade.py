"""High level application service used by the CLI (and usable as a library API)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from minescope.configuration.settings import Settings
from minescope.core.constants import DEFAULT_BEDROCK_PORT, DEFAULT_JAVA_PORT
from minescope.database.repository import Database, ScanRecord
from minescope.models.server import Edition, ScanResult, ServerTarget
from minescope.monitoring.monitor import Monitor
from minescope.scanner.batch import scan_many
from minescope.scanner.scanner import ServerScanner
from minescope.services.analytics import ServerStatistics, compute_statistics
from minescope.utils.address import parse_address


class MineScopeService:
    """Coordinates scanning, persistence and analytics."""

    def __init__(self, settings: Settings, scanner: Optional[ServerScanner] = None,
                 database: Optional[Database] = None, persist: bool = True) -> None:
        self.settings = settings
        self.scanner = scanner or ServerScanner(settings.timeout, settings.try_query)
        self._database = database
        self._persist = persist

    @property
    def database(self) -> Database:
        if self._database is None:
            self._database = Database(self.settings.database_path)
        return self._database

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
            self._database = None

    def __enter__(self) -> "MineScopeService":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @staticmethod
    def make_target(address: str, edition: str = "auto", name: str = "") -> ServerTarget:
        """Build a validated target from user input such as ``host:port``."""
        parsed = Edition.parse(edition)
        default = DEFAULT_BEDROCK_PORT if parsed is Edition.BEDROCK else DEFAULT_JAVA_PORT
        host, port = parse_address(address, default)
        return ServerTarget(host=host, port=port, edition=parsed, name=name)

    def _store(self, result: ScanResult) -> None:
        if self._persist:
            self.database.save_result(result)

    def scan(self, targets: Sequence[ServerTarget]) -> list[ScanResult]:
        """Scan targets concurrently and persist the results."""
        results = scan_many(targets, self.scanner.scan, self.settings.concurrency)
        for result in results:
            self._store(result)
        return results

    def monitor(self, targets: Sequence[ServerTarget],
                on_cycle: Optional[Callable[[int, list[ScanResult]], None]] = None,
                interval: Optional[float] = None) -> Monitor:
        """Create a :class:`Monitor` that persists every cycle."""

        def handle(cycle: int, results: list[ScanResult]) -> None:
            for result in results:
                self._store(result)
            if on_cycle is not None:
                on_cycle(cycle, results)

        return Monitor(targets, self.scanner.scan, interval or self.settings.monitor_interval,
                       self.settings.concurrency, handle)

    def history(self, target: ServerTarget, limit: Optional[int] = None,
                since: Optional[str] = None) -> list[ScanRecord]:
        return self.database.history(target.host, target.port, limit, since)

    def statistics(self, target: ServerTarget, since: Optional[str] = None) -> ServerStatistics:
        return compute_statistics(self.history(target, since=since))
