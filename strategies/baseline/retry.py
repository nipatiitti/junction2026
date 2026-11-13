"""How the baseline posts a leg again after a failed visit: the pickup time, and the facts the visit taught.

It is the organisers' code from `spread/starter.py`, unchanged. README.md next to this file says so.
"""

from __future__ import annotations

from typing import NamedTuple


class Retry(NamedTuple):
    """How to post a leg again after a failed visit."""

    pickup_from: int = 0
    manual_licence: bool = False
    plates: bool = False


FIRST_TRY = Retry()  # the default of `post`, as a singleton: a Retry never changes
