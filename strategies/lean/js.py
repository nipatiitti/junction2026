"""What the port needs to decide exactly as the TypeScript `lean` does: JavaScript's rounding, its 32-bit integer
arithmetic for the seeded draws, and an exponential that gives infinity where JavaScript does instead of raising."""

from __future__ import annotations

import math

INF = math.inf


def js_round(value: float) -> int:
    """`Math.round`: half rounds up, towards +infinity. Python's `round` rounds half to even."""
    return math.floor(value + 0.5)


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def exp(value: float) -> float:
    """`Math.exp`, which overflows to infinity."""
    return INF if value > 709 else math.exp(value)


def i32(value: int) -> int:
    """A number as JavaScript's bitwise operators see it: a signed 32-bit integer."""
    return ((value & 0xFFFFFFFF) ^ 0x80000000) - 0x80000000


def u32(value: int) -> int:
    """`value >>> 0`."""
    return value & 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    """`Math.imul`: the low 32 bits of the product, signed."""
    return i32(u32(a) * u32(b))


def day_of(minute: float) -> float:
    """`Math.floor(minute / DAY)`, which stays infinite for an infinite minute."""
    return math.floor(minute / (24 * 60)) if math.isfinite(minute) else minute
