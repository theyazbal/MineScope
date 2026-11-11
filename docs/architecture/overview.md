# Architecture

```
cli ──► services.facade ──► scanner ──► protocols (java/slp, java/query, bedrock/raknet)
 │            │                 │
 │            ├──► database (SQLite, migrations)         models / core / utils are shared
 │            ├──► monitoring (Monitor loop)
 │            └──► reporting (json / csv / html)
 └── ui (rich or plain renderer)
```

| Package | Responsibility |
| --- | --- |
| `protocols` | Wire formats only. Depend on injectable socket factories; know nothing about the terminal or database. |
| `scanner` | `ServerScanner` (one target, edition detection, optional Query) and `scan_many` (bounded thread pool). |
| `monitoring` | `Monitor`: repeat scans, callback per cycle, `stop()` for graceful shutdown. |
| `database` | `Database` repository (parameterized SQL, RLock, `PRAGMA user_version` migrations). |
| `services` | `analytics` (uptime, latency, outages) and `MineScopeService` facade used by the CLI. |
| `reporting` | Pure renderers plus atomic, sanitized file writing. |
| `configuration` | `Settings` dataclass, validation, JSON load/save. |
| `cli` | argparse commands, interactive menu, `Renderer` implementations. |

Design decisions:

- **Errors**: protocol/network problems become `MineScopeError` subclasses; the scanner converts them into
  an offline `ScanResult` with a message, so one bad server never aborts a batch.
- **Concurrency**: threads (I/O bound). Worker count is capped at `MAX_CONCURRENCY` (64).
  Java Query runs concurrently with the status ping and uses at most 1 s, because most servers leave Query disabled.
- **Testability**: clients accept `TcpConnector` / `UdpFactory` callables, so tests use fake sockets or loopback servers.
- **Schema changes**: append a migration to `database/migrations.py`; never edit old ones.

## Extending

Add a protocol by implementing `ProtocolClient.ping(host, port, timeout) -> PingResponse` and passing it to
`ServerScanner(...)`. Add a report format by adding a renderer to `reporting/exporters.py`'s `_RENDERERS`.
