"""Turns a note's facts into the stop windows of a gig, so a driver arrives when the car can be collected
and delivers by the note's deadline, inside the real opening hours."""

from __future__ import annotations

from spread.types import OpeningHours, TimeWindow

from strategies.notes.reader import DAY, NoteFacts

Snow = tuple[int, int]  # from, to: snow falls at a place in these minutes


def _open_on(day: int, hours: OpeningHours, facts_hours: tuple[int | None, int | None]) -> tuple[int, int] | None:
    """The real opening hours on a day (0 = the first Monday), or None when the site is closed. A note
    changes the weekday hours; Saturday keeps its stated hours."""
    weekday = day % 7
    if weekday == 5:
        saturday = hours.get("saturday")
        return (saturday["opens"], saturday["closes"]) if saturday else None
    if weekday not in hours["weekdays"]:
        return None
    opens, closes = facts_hours
    return (hours["opens"] if opens is None else opens, hours["closes"] if closes is None else closes)


def after_snow(start: int, snow: list[Snow]) -> int:
    """The first minute from `start` on that is not inside a snowfall."""
    moved = True
    while moved:
        moved = False
        for begins, ends in snow:
            if begins <= start < ends:
                start, moved = ends, True
    return start


def pickup_window(
    stated: TimeWindow,
    hours: OpeningHours | None,
    facts: NoteFacts,
    now: int,
    not_before: int = 0,
    snow: list[Snow] | None = None,
) -> TimeWindow | None:
    """The pickup window that the note needs from `now` on, or None when the order's own window will do.

    - The car is ready, or released after payment, at `facts.earliest_pickup`.
    - When the note gives the site's real hours, the window is one day inside them: the first day from the
      start on when the site is open. The driver plans by the stated hours, so a longer window could bring
      them after the real closing time.
    - A car on summer tyres cannot be collected while snow falls at either end: the window starts after it.
    """
    earliest = max(facts.earliest_pickup or 0, not_before)
    if facts.summer_tyres and snow:
        earliest = after_snow(max(earliest, now, stated["from"]), snow)
    real_hours = (facts.pickup_hours.opens, facts.pickup_hours.closes) if facts.pickup_hours else None
    if earliest <= now and not (real_hours and hours):
        return None  # the car is ready by now, and the stated hours are the real ones
    start = max(stated["from"], earliest, now)
    if real_hours and hours:
        for day in range(start // DAY, start // DAY + 14):
            open_hours = _open_on(day, hours, real_hours)
            if open_hours is None:
                continue
            begins, ends = max(start, day * DAY + open_hours[0]), day * DAY + open_hours[1]
            if begins < ends:
                return {"from": begins, "to": ends}
        return None
    if start <= stated["from"]:
        return None
    return {"from": start, "to": max(stated["to"], start)}


def delivery_window(base: TimeWindow, hours: OpeningHours | None, facts: NoteFacts) -> TimeWindow:
    """The delivery window by the note: it ends at a tighter deadline, and at the real closing time on its
    last day, so the driver does not arrive after closing and wait. It never ends before it starts."""
    end = base["to"]
    if facts.deadline is not None:
        end = min(end, facts.deadline)
    if hours and facts.delivery_hours:
        open_hours = _open_on(end // DAY, hours, (facts.delivery_hours.opens, facts.delivery_hours.closes))
        if open_hours is not None:
            end = min(end, end // DAY * DAY + open_hours[1])
    return {"from": base["from"], "to": end} if end >= base["from"] else base
