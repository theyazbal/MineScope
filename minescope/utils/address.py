"""Validation and parsing of server addresses."""

from __future__ import annotations

import ipaddress
import re

from minescope.core.errors import ValidationError

_HOST_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


def validate_port(port: int | str) -> int:
    """Return ``port`` as an int or raise :class:`ValidationError`."""
    try:
        value = int(port)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid port: {port!r}") from None
    if not 1 <= value <= 65535:
        raise ValidationError(f"Port out of range (1-65535): {value}")
    return value


def validate_host(host: str) -> str:
    """Validate a hostname or IP literal and return it normalized."""
    host = (host or "").strip()
    if not host:
        raise ValidationError("Host must not be empty")
    if len(host) > 253:
        raise ValidationError("Host is too long")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    labels = host.rstrip(".").split(".")
    if not all(_HOST_LABEL.match(label) for label in labels):
        raise ValidationError(f"Invalid host: {host!r}")
    return host.lower()


def parse_address(address: str, default_port: int) -> tuple[str, int]:
    """Split ``host[:port]`` (including ``[ipv6]:port``) into its parts."""
    text = (address or "").strip()
    if not text:
        raise ValidationError("Address must not be empty")
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            raise ValidationError(f"Invalid IPv6 address: {address!r}")
        host = text[1:end]
        rest = text[end + 1:]
        if rest and not rest.startswith(":"):
            raise ValidationError(f"Invalid address: {address!r}")
        port = validate_port(rest[1:]) if rest else default_port
        return validate_host(host), port
    if text.count(":") == 1:
        host, port_text = text.split(":")
        return validate_host(host), validate_port(port_text)
    if text.count(":") > 1:
        return validate_host(text), default_port  # bare IPv6 literal
    return validate_host(text), default_port
