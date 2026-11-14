"""Special-delivery requirements, and the multiplicative premium they add to the quote and the driver fee.

The requirements that narrow the driver audience: a premium car needs an experienced driver, and a manual car needs a
manual licence. Each requirement multiplies by `1 + SPECIAL_SHARE`, so `n` requirements give `1.05 ** n` — 1.0, 1.05,
1.1025 for none, one or two. The same factor reaches the quote (`pricing.py`), the admission's expected cost
(`admission.py`) and the posted driver fee (`fees.py`), so the dealer pays it and the driver gets it.
"""

from __future__ import annotations

from strategies.notes import NoteReader

SPECIAL_SHARE = 0.05  # each special requirement adds this share, compounding


def count(request: dict, notes: NoteReader) -> int:
    """How many special requirements the request has: experienced (a premium car) and manual (a manual gearbox)."""
    premium = any(leg["car"]["premium"] for leg in request["legs"])
    manual = notes.read(request).manual
    return int(premium) + int(manual)


def factor(request: dict, notes: NoteReader) -> float:
    """The multiplier for the request's special requirements: 1 for none, `1 + SPECIAL_SHARE` for each."""
    return (1 + SPECIAL_SHARE) ** count(request, notes)
