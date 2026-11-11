"""SQLite repository for scan history. All SQL is parameterized."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from minescope.core.errors import DatabaseError
from minescope.database.migrations import current_version, migrate
from minescope.models.server import ScanResult


@dataclass
class ScanRecord:
    """A stored scan row."""

    server_id: int
    host: str
    port: int
    name: str
    scanned_at: str
    online: bool
    edition: str
    latency_ms: Optional[float]
    version: Optional[str]
    motd: Optional[str]
    players_online: Optional[int]
    players_max: Optional[int]
    player_names: list[str]
    error: Optional[str]


_SELECT = """
SELECT s.id, s.host, s.port, s.name, c.scanned_at, c.online, c.edition, c.latency_ms,
       c.version, c.motd, c.players_online, c.players_max, c.player_names, c.error
FROM scans c JOIN servers s ON s.id = c.server_id
"""


def _record(row: tuple[Any, ...]) -> ScanRecord:
    try:
        names = json.loads(row[12])
    except (TypeError, json.JSONDecodeError):
        names = []
    return ScanRecord(row[0], row[1], row[2], row[3], row[4], bool(row[5]), row[6],
                      row[7], row[8], row[9], row[10], row[11], names, row[13])


class Database:
    """Thread-safe SQLite store. Use as a context manager or call :meth:`close`."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON")
            migrate(self._conn)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot open database {self.path}: {exc}") from None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    @property
    def schema_version(self) -> int:
        with self._lock:
            return current_version(self._conn)

    def save_result(self, result: ScanResult) -> int:
        """Persist ``result`` and return the new scan row id."""
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO servers (host, port, name, edition) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(host, port) DO UPDATE SET name = excluded.name, "
                    "edition = CASE WHEN excluded.edition = 'unknown' THEN servers.edition "
                    "ELSE excluded.edition END",
                    (result.host, result.port, result.name, result.edition))
                server_id = self._conn.execute(
                    "SELECT id FROM servers WHERE host = ? AND port = ?",
                    (result.host, result.port)).fetchone()[0]
                cursor = self._conn.execute(
                    "INSERT INTO scans (server_id, scanned_at, online, edition, latency_ms, "
                    "version, motd, players_online, players_max, player_names, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (server_id, result.scanned_at, int(result.online), result.edition,
                     result.latency_ms, result.version, result.motd, result.players_online,
                     result.players_max, json.dumps(result.player_names, ensure_ascii=False),
                     result.error))
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot save scan result: {exc}") from None

    def servers(self) -> list[tuple[int, str, int, str]]:
        """Return ``(id, host, port, name)`` for every known server."""
        with self._lock:
            return [tuple(r) for r in self._conn.execute(  # type: ignore[misc]
                "SELECT id, host, port, name FROM servers ORDER BY host, port")]

    def history(self, host: str, port: int, limit: Optional[int] = None,
                since: Optional[str] = None) -> list[ScanRecord]:
        """Return scans for a server, oldest first."""
        query = _SELECT + " WHERE s.host = ? AND s.port = ?"
        params: list[Any] = [host, port]
        if since:
            query += " AND c.scanned_at >= ?"
            params.append(since)
        if limit is not None:
            query = ("SELECT * FROM (" + query + " ORDER BY c.scanned_at DESC, c.id DESC LIMIT ?)"
                     " ORDER BY scanned_at ASC")
            params.append(int(limit))
        else:
            query += " ORDER BY c.scanned_at ASC, c.id ASC"
        try:
            with self._lock:
                return [_record(r) for r in self._conn.execute(query, params)]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot read history: {exc}") from None

    def latest(self) -> list[ScanRecord]:
        """Return the most recent scan of every server."""
        query = _SELECT + (" WHERE c.id = (SELECT MAX(id) FROM scans WHERE server_id = s.id)"
                           " ORDER BY s.host, s.port")
        with self._lock:
            return [_record(r) for r in self._conn.execute(query)]

    def purge_before(self, iso_timestamp: str) -> int:
        """Delete scans older than ``iso_timestamp``; return rows removed."""
        with self._lock, self._conn:
            return self._conn.execute(
                "DELETE FROM scans WHERE scanned_at < ?", (iso_timestamp,)).rowcount
