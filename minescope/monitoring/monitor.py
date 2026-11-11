"""Repeating scan loop with graceful shutdown."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Sequence

from minescope.models.server import ScanResult, ServerTarget
from minescope.scanner.batch import ScanFunc, scan_many

log = logging.getLogger(__name__)

CycleCallback = Callable[[int, list[ScanResult]], None]


class Monitor:
    """Scan targets every ``interval`` seconds until stopped."""

    def __init__(self, targets: Sequence[ServerTarget], scan: ScanFunc,
                 interval: float, concurrency: int = 8,
                 on_cycle: Optional[CycleCallback] = None) -> None:
        self.targets = list(targets)
        self.interval = interval
        self.concurrency = concurrency
        self._scan = scan
        self._on_cycle = on_cycle
        self._stop = threading.Event()
        self.cycles_completed = 0

    @property
    def stop_event(self) -> threading.Event:
        return self._stop

    def stop(self) -> None:
        """Request shutdown; the current cycle finishes, no new one starts."""
        self._stop.set()

    def run(self, max_cycles: Optional[int] = None) -> int:
        """Run until :meth:`stop` is called or ``max_cycles`` cycles are done."""
        while not self._stop.is_set():
            results = scan_many(self.targets, self._scan, self.concurrency, self._stop)
            self.cycles_completed += 1
            if self._on_cycle is not None:
                try:
                    self._on_cycle(self.cycles_completed, results)
                except Exception:  # noqa: BLE001 - a callback must not kill monitoring
                    log.exception("monitor callback failed")
            if max_cycles is not None and self.cycles_completed >= max_cycles:
                break
            self._stop.wait(self.interval)
        return self.cycles_completed
