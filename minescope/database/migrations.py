"""Schema versioning via ``PRAGMA user_version``.

Add new migrations to the end of ``MIGRATIONS``; never edit existing ones.
"""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[str] = [
    # version 1
    """
    CREATE TABLE servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host TEXT NOT NULL,
        port INTEGER NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        edition TEXT NOT NULL DEFAULT 'unknown',
        UNIQUE (host, port)
    );
    CREATE TABLE scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
        scanned_at TEXT NOT NULL,
        online INTEGER NOT NULL CHECK (online IN (0, 1)),
        edition TEXT NOT NULL,
        latency_ms REAL,
        version TEXT,
        motd TEXT,
        players_online INTEGER,
        players_max INTEGER,
        player_names TEXT NOT NULL DEFAULT '[]',
        error TEXT
    );
    CREATE INDEX idx_scans_server_time ON scans(server_id, scanned_at);
    """,
]


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations and return the resulting schema version."""
    version = current_version(conn)
    for index in range(version, len(MIGRATIONS)):
        conn.executescript("BEGIN;" + MIGRATIONS[index] + f"PRAGMA user_version = {index + 1};COMMIT;")
    return current_version(conn)
