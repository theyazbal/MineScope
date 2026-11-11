"""Historical statistics computed from stored scan records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

from minescope.database.repository import ScanRecord


@dataclass
class ServerStatistics:
    """Aggregated statistics for one server."""

    checks: int
    online_checks: int
    uptime_percent: Optional[float]
    latency_avg_ms: Optional[float]
    latency_min_ms: Optional[float]
    latency_max_ms: Optional[float]
    players_avg: Optional[float]
    players_peak: Optional[int]
    outages: int
    longest_outage_checks: int
    first_seen: Optional[str]
    last_seen: Optional[str]
    last_online: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_statistics(records: Sequence[ScanRecord]) -> ServerStatistics:
    """Compute uptime, latency, player and outage statistics."""
    checks = len(records)
    online = [r for r in records if r.online]
    latencies = [r.latency_ms for r in online if r.latency_ms is not None]
    players = [r.players_online for r in online if r.players_online is not None]
    outages = longest = run = 0
    for record in records:
        if record.online:
            run = 0
        else:
            if run == 0:
                outages += 1
            run += 1
            longest = max(longest, run)
    return ServerStatistics(
        checks=checks,
        online_checks=len(online),
        uptime_percent=round(100 * len(online) / checks, 2) if checks else None,
        latency_avg_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
        latency_min_ms=min(latencies) if latencies else None,
        latency_max_ms=max(latencies) if latencies else None,
        players_avg=round(sum(players) / len(players), 2) if players else None,
        players_peak=max(players) if players else None,
        outages=outages,
        longest_outage_checks=longest,
        first_seen=records[0].scanned_at if records else None,
        last_seen=records[-1].scanned_at if records else None,
        last_online=online[-1].scanned_at if online else None,
    )


def parse_since(value: str) -> str:
    """Convert ``24h``, ``7d``, ``30m`` or an ISO date to an ISO timestamp."""
    from datetime import timedelta, timezone

    from minescope.core.errors import ValidationError
    text = value.strip().lower()
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    if text and text[-1] in units and text[:-1].isdigit():
        delta = timedelta(**{units[text[-1]]: int(text[:-1])})
        return (datetime.now(timezone.utc) - delta).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError(f"Invalid time window: {value!r} (use e.g. 24h, 7d or an ISO date)") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat(timespec="seconds")
