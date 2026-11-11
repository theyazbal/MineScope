# MineScope

**MineScope — Minecraft Server Intelligence Platform**
Version 1.0.0 · by **DevStudio** · Owner: [TheYAZBAL](https://github.com/TheYAZBAL)

MineScope scans, monitors and reports on **Minecraft Java and Bedrock servers**. Protocols are implemented
natively (no `mcstatus`), the runtime needs **no third-party packages**, and an optional `rich` interface gives
a dark, clean terminal UI.

> Only scan servers you own or are authorized to monitor. MineScope contacts only the targets you give it.

## Features

- Java **Server List Ping** (version, protocol, MOTD, players, sample names, latency).
- Java **Query** (GameSpy4 full stat) where `enable-query=true`: real player names, software, plugins, world.
- Bedrock **RakNet Unconnected Ping** (version, MOTD, players, world name, game mode, latency).
- **Automatic edition detection** (Java and Bedrock probed in parallel).
- **Concurrent** multi-server scanning with a bounded worker pool; **continuous monitoring** with graceful shutdown.
- **SQLite** history with schema versioning, **uptime / latency / player / outage** statistics.
- **JSON, CSV and HTML** reports.
- JSON configuration with validation; interactive menu; scriptable CLI with exit codes.

### Honest limits of the protocols

- The Bedrock status ping **does not expose player names**; MineScope shows counts only and never invents names.
- Java player names appear only if the server's status sample includes them or Query is enabled.
- Java SRV DNS records (`_minecraft._tcp`) are **not** resolved (the standard library has no SRV resolver);
  pass the real host and port.

## Install

Requires Python 3.10+ (Windows 10/11 and Linux).

```bash
git clone https://github.com/TheYAZBAL/MineScope.git
cd MineScope
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux: source .venv/bin/activate
python -m pip install -e ".[rich]"      # or just: python main.py (no install, stdlib only)
```

## Usage

```bash
minescope                                   # interactive menu
minescope scan play.example.net             # auto-detect edition (ports: 25565 Java / 19132 Bedrock)
minescope scan play.example.net:25565 -e java -r html -r json
minescope scan -e bedrock bedrock.example.net --fail-offline   # exit code 3 if offline
minescope monitor play.example.net -i 30    # Ctrl+C stops after the current cycle
minescope history play.example.net --since 24h
minescope stats play.example.net --since 7d
minescope report html                       # report from the latest stored results
minescope config init                       # writes minescope.json with placeholder hosts
minescope about
```

Without installing, use `python main.py <command>` or `python -m minescope <command>`.
Add `--plain` for output without `rich`.

### Configuration

`minescope.json` (see [examples/minescope.example.json](examples/minescope.example.json)):

```json
{
  "settings": { "timeout": 3.0, "concurrency": 8, "monitor_interval": 30, "try_query": true,
                "database_path": "data/minescope.db", "report_dir": "reports", "log_level": "WARNING" },
  "servers": [ { "name": "My Java", "edition": "java", "address": "play.example.net:25565" } ]
}
```

A bare JSON list of servers (the old `servers.json` format) is also accepted.

### Exit codes

`0` success · `1` runtime error · `2` invalid input/usage · `3` offline target with `--fail-offline` · `130` interrupted.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .        # works with the standard library alone
python -m pytest --cov=minescope                 # if pytest/pytest-cov are installed
ruff check minescope tests
```

Docs: [architecture](docs/architecture/overview.md) · [development](docs/development/setup.md) ·
[API](docs/api/library.md) · [installation](docs/installation/install.md) · [user guide](docs/user-guide/guide.md).
See also [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [CHANGELOG](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
