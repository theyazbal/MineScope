"""Dataclasses describing scan targets and scan results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Edition(str, Enum):
    """Supported Minecraft editions."""

    JAVA = "java"
    BEDROCK = "bedrock"
    AUTO = "auto"

    @classmethod
    def parse(cls, value: str) -> "Edition":
        """Parse a user supplied edition name."""
        normalized = (value or "").strip().lower()
        aliases = {"j": cls.JAVA, "java": cls.JAVA, "b": cls.BEDROCK, "be": cls.BEDROCK,
                   "bedrock": cls.BEDROCK, "auto": cls.AUTO, "a": cls.AUTO}
        if normalized not in aliases:
            from minescope.core.errors import ValidationError
            raise ValidationError(f"Unknown edition: {value!r} (use java, bedrock or auto)")
        return aliases[normalized]


@dataclass(frozen=True)
class ServerTarget:
    """A server explicitly supplied or configured by the user."""

    host: str
    port: int
    edition: Edition = Edition.AUTO
    name: str = ""
    query_port: Optional[int] = None

    @property
    def address(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    @property
    def label(self) -> str:
        return self.name or self.address


@dataclass
class StatusSnapshot:
    """Raw, protocol level status information."""

    version: Optional[str] = None
    protocol: Optional[int] = None
    motd: Optional[str] = None
    players_online: Optional[int] = None
    players_max: Optional[int] = None
    player_names: list[str] = field(default_factory=list)
    gamemode: Optional[str] = None
    map_name: Optional[str] = None
    server_id: Optional[str] = None
    software: Optional[str] = None
    plugins: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ScanResult:
    """Outcome of scanning a single target."""

    name: str
    host: str
    port: int
    edition: str
    online: bool
    latency_ms: Optional[float] = None
    version: Optional[str] = None
    protocol: Optional[int] = None
    motd: Optional[str] = None
    players_online: Optional[int] = None
    players_max: Optional[int] = None
    player_names: list[str] = field(default_factory=list)
    gamemode: Optional[str] = None
    map_name: Optional[str] = None
    software: Optional[str] = None
    plugins: list[str] = field(default_factory=list)
    query_available: bool = False
    error: Optional[str] = None
    scanned_at: str = field(default_factory=utc_now_iso)

    @property
    def address(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["address"] = self.address
        return data
