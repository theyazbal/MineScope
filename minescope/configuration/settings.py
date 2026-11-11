"""Settings dataclass plus JSON configuration file handling.

Two file layouts are accepted:

* ``{"settings": {...}, "servers": [...]}`` (preferred), and
* a bare JSON list of server objects (legacy ``servers.json`` style).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from minescope.core import constants as c
from minescope.core.errors import ConfigurationError, ValidationError
from minescope.models.server import Edition, ServerTarget
from minescope.utils.address import parse_address, validate_host, validate_port

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass
class Settings:
    """Validated runtime settings."""

    timeout: float = c.DEFAULT_TIMEOUT
    concurrency: int = c.DEFAULT_CONCURRENCY
    monitor_interval: float = c.DEFAULT_MONITOR_INTERVAL
    try_query: bool = True
    database_path: str = "data/minescope.db"
    report_dir: str = "reports"
    log_level: str = "WARNING"
    log_file: str | None = None
    structured_logs: bool = False
    servers: list[ServerTarget] = field(default_factory=list)

    def validate(self) -> "Settings":
        if not c.MIN_TIMEOUT <= self.timeout <= c.MAX_TIMEOUT:
            raise ConfigurationError(
                f"timeout must be between {c.MIN_TIMEOUT} and {c.MAX_TIMEOUT} seconds")
        if not 1 <= self.concurrency <= c.MAX_CONCURRENCY:
            raise ConfigurationError(f"concurrency must be between 1 and {c.MAX_CONCURRENCY}")
        if self.monitor_interval < c.MIN_MONITOR_INTERVAL:
            raise ConfigurationError(
                f"monitor_interval must be at least {c.MIN_MONITOR_INTERVAL} seconds")
        if self.log_level.upper() not in _LOG_LEVELS:
            raise ConfigurationError(f"log_level must be one of {sorted(_LOG_LEVELS)}")
        self.log_level = self.log_level.upper()
        if not self.database_path or not self.report_dir:
            raise ConfigurationError("database_path and report_dir must not be empty")
        return self


def parse_server(entry: Any, index: int = 0) -> ServerTarget:
    """Build a :class:`ServerTarget` from a configuration entry."""
    if not isinstance(entry, dict):
        raise ConfigurationError(f"servers[{index}] must be an object")
    try:
        edition = Edition.parse(str(entry.get("edition", "auto")))
        default_port = (c.DEFAULT_BEDROCK_PORT if edition is Edition.BEDROCK
                        else c.DEFAULT_JAVA_PORT)
        if "address" in entry:
            host, port = parse_address(str(entry["address"]), default_port)
        elif "host" in entry:
            host = validate_host(str(entry["host"]))
            port = validate_port(entry.get("port", default_port))
        else:
            raise ConfigurationError(f"servers[{index}] needs 'address' or 'host'")
        query_port = entry.get("query_port")
        if query_port is not None:
            query_port = validate_port(query_port)
    except ValidationError as exc:
        raise ConfigurationError(f"servers[{index}]: {exc}") from None
    name = str(entry.get("name", "")).strip()[:100]
    return ServerTarget(host=host, port=port, edition=edition, name=name, query_port=query_port)


def _from_document(document: Any) -> Settings:
    if isinstance(document, list):
        document = {"servers": document}
    if not isinstance(document, dict):
        raise ConfigurationError("Configuration root must be an object or a list")
    raw = document.get("settings", {})
    if not isinstance(raw, dict):
        raise ConfigurationError("'settings' must be an object")
    known = {k for k in Settings.__dataclass_fields__ if k != "servers"}
    unknown = set(raw) - known
    if unknown:
        raise ConfigurationError(f"Unknown settings: {', '.join(sorted(unknown))}")
    try:
        settings = Settings(**raw)
    except TypeError as exc:
        raise ConfigurationError(f"Invalid settings: {exc}") from None
    servers = document.get("servers", [])
    if not isinstance(servers, list):
        raise ConfigurationError("'servers' must be a list")
    settings.servers = [parse_server(e, i) for i, e in enumerate(servers)]
    try:
        settings.timeout = float(settings.timeout)
        settings.concurrency = int(settings.concurrency)
        settings.monitor_interval = float(settings.monitor_interval)
    except (TypeError, ValueError):
        raise ConfigurationError("timeout, concurrency and monitor_interval must be numbers") from None
    return settings.validate()


def load_config(path: str | os.PathLike[str] | None) -> Settings:
    """Load settings from ``path``; return defaults if ``path`` is None/missing."""
    if path is None:
        return Settings().validate()
    file = Path(path)
    if not file.exists():
        return Settings().validate()
    try:
        document = json.loads(file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{file}: invalid JSON ({exc})") from None
    except OSError as exc:
        raise ConfigurationError(f"{file}: cannot be read ({exc.strerror})") from None
    return _from_document(document)


def to_document(settings: Settings) -> dict[str, Any]:
    data = asdict(settings)
    data.pop("servers")
    out_servers = []
    for target in settings.servers:
        entry: dict[str, Any] = {"name": target.name, "edition": target.edition.value,
                                 "address": target.address}
        if target.query_port:
            entry["query_port"] = target.query_port
        out_servers.append(entry)
    return {"settings": data, "servers": out_servers}


def save_config(settings: Settings, path: str | os.PathLike[str]) -> Path:
    """Atomically write ``settings`` to ``path`` as JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(to_document(settings), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, target)
    except OSError as exc:
        Path(tmp).unlink(missing_ok=True)
        raise ConfigurationError(f"Cannot write {target}: {exc.strerror}") from None
    return target


def write_example_config(path: str | os.PathLike[str], overwrite: bool = False) -> Path:
    """Write an example configuration file (placeholder hosts, not real servers)."""
    target = Path(path)
    if target.exists() and not overwrite:
        raise ConfigurationError(f"{target} already exists (use --force to overwrite)")
    example = Settings(servers=[
        ServerTarget("play.example.net", 25565, Edition.JAVA, "Example Java"),
        ServerTarget("bedrock.example.net", 19132, Edition.BEDROCK, "Example Bedrock"),
    ])
    return save_config(example, target)
