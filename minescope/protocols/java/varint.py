"""Minecraft VarInt and string primitives."""

from __future__ import annotations

from typing import Callable

from minescope.core.errors import ProtocolError


def encode_varint(value: int) -> bytes:
    """Encode a signed 32-bit integer as a Minecraft VarInt."""
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(read_byte: Callable[[], int]) -> int:
    """Decode a VarInt, pulling one byte at a time from ``read_byte``."""
    result = 0
    for shift in range(0, 35, 7):
        byte = read_byte()
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if result & 0x80000000:
                result -= 1 << 32
            return result
    raise ProtocolError("VarInt is too long")


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode a VarInt from ``data``; return ``(value, new_offset)``."""
    position = offset

    def next_byte() -> int:
        nonlocal position
        if position >= len(data):
            raise ProtocolError("Truncated VarInt")
        position += 1
        return data[position - 1]

    value = read_varint(next_byte)
    return value, position


def encode_string(text: str) -> bytes:
    """Encode a length-prefixed UTF-8 string."""
    raw = text.encode("utf-8")
    return encode_varint(len(raw)) + raw
