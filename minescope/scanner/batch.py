"""Bounded concurrent scanning of many targets."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Optional

from minescope.core.constants import MAX_CONCURRENCY
from minescope.models.server import ScanResult, ServerTarget

ScanFunc = Callable[[ServerTarget], ScanResult]


def scan_many(targets: Iterable[ServerTarget], scan: ScanFunc, concurrency: int = 8,
              stop_event: Optional[threading.Event] = None,
              on_result: Optional[Callable[[ScanResult], None]] = None) -> list[ScanResult]:
    """Scan ``targets`` with at most ``concurrency`` workers.

    Results are returned in input order. Targets not yet started when
    ``stop_event`` is set are skipped, so shutdown is prompt.
    """
    items = list(targets)
    workers = max(1, min(int(concurrency), MAX_CONCURRENCY, len(items) or 1))
    results: list[Optional[ScanResult]] = [None] * len(items)

    def run(index: int) -> None:
        if stop_event is not None and stop_event.is_set():
            return
        result = scan(items[index])
        results[index] = result
        if on_result is not None:
            on_result(result)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="minescope-scan") as pool:
        futures = [pool.submit(run, i) for i in range(len(items))]
        for future in futures:
            future.result()
    return [r for r in results if r is not None]
