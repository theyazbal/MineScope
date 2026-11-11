"""Exception hierarchy and centralized error formatting."""

from __future__ import annotations


class MineScopeError(Exception):
    """Base class for all MineScope errors."""


class ValidationError(MineScopeError):
    """Raised when user supplied input is invalid."""


class ConfigurationError(MineScopeError):
    """Raised when configuration is missing or invalid."""


class ProtocolError(MineScopeError):
    """Raised when a server response violates the protocol."""


class ConnectionFailure(MineScopeError):
    """Raised when a server cannot be reached."""


class ServerTimeout(ConnectionFailure):
    """Raised when a server does not answer in time."""


class DatabaseError(MineScopeError):
    """Raised for persistence failures."""


class ReportError(MineScopeError):
    """Raised when a report cannot be produced."""


def describe_error(exc: BaseException) -> str:
    """Return a short, safe, human readable description of ``exc``."""
    if isinstance(exc, MineScopeError):
        return str(exc) or exc.__class__.__name__
    if isinstance(exc, TimeoutError):
        return "Connection timed out"
    if isinstance(exc, ConnectionRefusedError):
        return "Connection refused"
    if isinstance(exc, OSError):
        return f"Network error: {exc.strerror or exc}"
    return f"{exc.__class__.__name__}: {exc}"
