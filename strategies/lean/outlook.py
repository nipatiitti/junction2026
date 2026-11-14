"""The order model (`outlook.ts`, weights in `order.json`, a copy of src/strategies/lean/order.json): what a won order
costs to serve over its typical fee (fees, failed visits, waiting), and the chance that it arrives late, from what the
desk sees at the quote. The level of the cost stays the week's own; the model says which requests are dear and which
are risky."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from strategies.lean.js import clamp, exp

HOUR, DAY = 60, 24 * 60
ORDER_JSON = Path(__file__).with_name("order.json")


@dataclass(frozen=True)
class Work:
    """A request as the model sees it, at the minute `at`."""

    typical_cents: float
    at: int
    ready_at: float
    last_pickup_at: float
    deadline: float
    drive_minutes: float
    private_pickup: bool
    private_delivery: bool
    premium: bool
    electric: bool
    trade_in: bool
    has_note: bool
    home_pickup: int  # drivers of this week's list who live at the pickup place
    home_delivery: int
    drivers: int
    won: int  # our orders won so far in the week
    won_today: int
    open: int  # our gigs open without a driver now


def load_orders() -> dict:
    return json.loads(ORDER_JSON.read_text())


def outlook(model: dict, work: Work) -> tuple[float, float]:
    """What the model expects of this work, won now: its cost over the mean order's, and its chance to be late."""
    offset = math.floor(work.ready_at / DAY) - math.floor(work.at / DAY)
    hour = (work.at % DAY) / HOUR
    day = math.floor(work.at / DAY)
    today = 1 if offset <= 0 else 0
    drive = work.drive_minutes / 60
    log_typical = math.log(max(1, work.typical_cents) / 5000)
    to_last = (work.last_pickup_at - work.at) / HOUR
    long = clamp(drive - 3, 0, 6) / 6
    x = {
        "log_typical": log_typical,
        "log_typical_sq": log_typical * log_typical,
        "pickup_today": today,
        "pickup_later": 1 if offset >= 2 else 0,
        "hour": (hour - 13) / 5,
        "today_late_hour": (today * clamp(hour - 12, 0, 6)) / 6,
        "long_drive": long,
        "very_long_drive": clamp(drive - 5, 0, 4) / 4,
        "short_drive": 1 if drive < 0.75 else 0,
        "today_long_drive": today * long,
        "time_to_last_pickup": math.log(clamp(to_last, 1, 96) / 24),
        "tight": 1 if to_last < 8 else 0,
        "room": math.log(clamp((work.deadline - work.ready_at) / HOUR, 2, 120) / 24),
        "monday": 1 if day == 0 else 0,
        "thursday": 1 if day == 3 else 0,
        "friday": 1 if day == 4 else 0,
        "private_pickup": 1 if work.private_pickup else 0,
        "private_delivery": 1 if work.private_delivery else 0,
        "premium": 1 if work.premium else 0,
        "electric": 1 if work.electric else 0,
        "trade_in": 1 if work.trade_in else 0,
        "has_note": 1 if work.has_note else 0,
        "home_pickup": math.log(1 + work.home_pickup) / 5,
        "home_delivery": math.log(1 + work.home_delivery) / 5,
        "drivers": math.log(max(1, work.drivers) / 777),
        "won_so_far": work.won / 300,
        "won_today": work.won_today / 80,
        "open_gigs": clamp(work.open, 0, 120) / 40,
    }

    def total(weights: dict) -> float:
        value = weights.get("base", 0)
        for key, feature in x.items():
            value += weights.get(key, 0) * feature
        return value

    cost = clamp(total(model["cost"]) / model["meanCost"], 0.5, 3)
    return cost, 1 / (1 + exp(-total(model["late"])))
