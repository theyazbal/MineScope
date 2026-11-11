"""Flatten Minecraft chat components and legacy formatting to plain text."""

from __future__ import annotations

import re
from typing import Any

_LEGACY = re.compile("§[0-9A-FK-ORa-fk-or]")


def strip_formatting(text: str) -> str:
    """Remove legacy ``§x`` formatting codes."""
    return _LEGACY.sub("", text)


def flatten_component(component: Any, _depth: int = 0) -> str:
    """Convert a chat component (string, dict or list) to plain text."""
    if _depth > 32:
        return ""
    if component is None:
        return ""
    if isinstance(component, str):
        return strip_formatting(component)
    if isinstance(component, (int, float, bool)):
        return str(component)
    if isinstance(component, list):
        return "".join(flatten_component(part, _depth + 1) for part in component)
    if isinstance(component, dict):
        text = flatten_component(component.get("text", ""), _depth + 1)
        extra = component.get("extra")
        if extra:
            text += flatten_component(extra, _depth + 1)
        return text
    return ""
