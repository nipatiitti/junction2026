"""Turns weeks saved by scrape.py into distributions for an offline model of the server. Needs no network.

    uv run python -m tools.stats                                        # the team's committed weeks in data/scrape
    uv run python -m tools.stats out/scrape/passive out/scrape/explore  # weeks from your own scrape

Without folders, reads data/scrape and writes out/summary.json. With folders, writes summary.json into the first
folder. --out chooses another file. Prints the main numbers. Groups are "L<level>/<policy>", or
"L<level>/<policy>-<tag>" for a scrape with --tag.
tools/README.md lists what the summary holds.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any, NamedTuple

OFFLINE_DATA = Path(__file__).parents[1] / "data" / "scrape"  # the team's committed scrape: no server needed
HOUR, DAY = 60, 24 * 60
MAX_ENUM = 30  # a text or bool field with more distinct values than this is not an enumeration
RATIO_BIN = 0.05  # width of the bins of quote / list price
FEE_BIN = 0.2  # width of the bins of opening fee / typical fee


class Week(NamedTuple):
    meta: dict
    events: list[dict]
    reveal: dict
    snapshot: dict
    drivers: list[dict]
    # Saved by scrape.py since #49; empty for older weeks and for weeks that a killed scrape left behind.
    actions: Sequence[dict] = ()  # each action sent, with its minute and result
    rosters: Sequence[dict] = ()  # the driver list at each midnight and at the end: {at, drivers}
    positions: Sequence[dict] = ()  # samples of our drivers' positions: {at, positions}


def read_json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text())


def read_lines(path: Path) -> list[dict]:
    """The rows of a .jsonl.gz file; none when the file is missing."""
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_week(folder: Path) -> Week:
    return Week(
        read_json(folder / "meta.json"),
        read_lines(folder / "events.jsonl.gz"),
        read_json(folder / "reveal.json.gz"),
        read_json(folder / "snapshot.json.gz"),
        read_json(folder / "drivers.json.gz"),
        read_lines(folder / "actions.jsonl.gz"),
        read_lines(folder / "rosters.jsonl.gz"),
        read_lines(folder / "positions.jsonl.gz"),
    )


def find_weeks(roots: Iterable[Path]) -> Iterator[Path]:
    """The folders of the saved weeks. A folder of the prober (`sim/prober.ts`, as under `data/scrape/probe2`) has a
    `meta.json` too, but no snapshot: it is not a saved week, so it is skipped."""
    for root in roots:
        for meta in sorted(root.rglob("meta.json")):
            if not meta.parent.name.endswith(".partial") and (meta.parent / "snapshot.json.gz").exists():
                yield meta.parent


def load_map(roots: Iterable[Path]) -> dict | None:
    """The map that scrape.py saved in an output folder, also when given a folder above it. Every week has the same map."""
    for root in roots:
        for path in sorted(root.rglob("map.json")):
            return read_json(path)
    return None


# Summaries of numbers


def quantiles(values: list[float]) -> dict:
    """n, mean, sd, min, p5, p25, p50, p75, p95 and max of the values; only n when there are none."""
    if not values:
        return {"n": 0}
    xs = sorted(values)
    n = len(xs)
    mean = sum(xs) / n

    def q(p: float) -> float:
        i = p * (n - 1)
        lo = math.floor(i)
        return xs[lo] + (xs[min(lo + 1, n - 1)] - xs[lo]) * (i - lo)

    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / n)
    result = {"mean": mean, "sd": sd, "min": xs[0]}
    result |= {f"p{round(p * 100)}": q(p) for p in (0.05, 0.25, 0.5, 0.75, 0.95)}
    return {"n": n} | {k: round(v, 4) for k, v in (result | {"max": xs[-1]}).items()}


def fit_line(points: list[tuple[float, float]]) -> dict:
    """Least squares y = intercept + slope * x, with the sd of the residual relative to y."""
    if len(points) < 2:
        return {"n": len(points)}
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx if sxx else 0.0
    intercept = my - slope * mx
    rel = [(y - intercept - slope * x) / y for x, y in points if y]
    return {
        "n": n,
        "intercept": round(intercept, 3),
        "slope": round(slope, 4),
        "relativeResidualSd": round(math.sqrt(sum(r * r for r in rel) / len(rel)), 4) if rel else None,
    }


def shares(counter: Counter, total: int | None = None) -> dict:
    total = total if total is not None else sum(counter.values())
    return {str(k): {"count": v, "share": round(v / total, 4) if total else None} for k, v in counter.most_common()}


# The event catalogue: every kind, its fields and their values


def walk(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """(path, leaf) for every leaf of a JSON value; list items share the path `<list>[]`."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        if not value:
            yield f"{path}[]", "<empty>"
        for item in value:
            yield from walk(item, f"{path}[]")
    else:
        yield path, value


def type_name(value: Any) -> str:
    return {bool: "bool", int: "int", float: "float", str: "str", type(None): "null"}.get(type(value), "other")


class Catalogue:
    """For each event kind: its count, the levels it came in, each field's types and range, and the values of each
    field that looks like an enumeration."""

    def __init__(self) -> None:
        self.kinds: dict[str, dict] = {}

    def add(self, group: str, event: dict) -> None:
        entry = self.kinds.setdefault(
            event["kind"],
            {
                "count": 0,
                "groups": Counter(),
                "fields": defaultdict(Counter),
                "values": defaultdict(Counter),
                "range": {},
                "example": event,
            },
        )
        entry["count"] += 1
        entry["groups"][group] += 1
        for path, leaf in walk(event):
            if path in ("seq", "kind"):
                continue
            entry["fields"][path][type_name(leaf)] += 1
            if isinstance(leaf, (int, float)) and not isinstance(leaf, bool):
                low, high = entry["range"].get(path, (leaf, leaf))
                entry["range"][path] = (min(low, leaf), max(high, leaf))
            else:  # text, bool or null: counted until it has too many values to be an enumeration
                values = entry["values"][path]
                if len(values) <= MAX_ENUM:
                    values[leaf] += 1

    def summary(self) -> dict:
        out = {}
        for kind, entry in sorted(self.kinds.items()):
            enums = {
                path: dict(values.most_common())
                for path, values in entry["values"].items()
                if len(values) <= MAX_ENUM and not path.endswith(("Id", "id", "Ids[]", "text", "detail"))
            }
            out[kind] = {
                "count": entry["count"],
                "groups": dict(entry["groups"]),
                "fields": {path: dict(types) for path, types in sorted(entry["fields"].items())},
                "range": {path: list(r) for path, r in sorted(entry["range"].items())},
                "enumerations": enums,
                "example": entry["example"],
            }
        return out


# Statistics of one group of weeks


class Group:
    """Collects the numbers of every week of one level and policy."""

    def __init__(self, km: dict[tuple[str, str], float], minutes: dict[tuple[str, str], int], names: dict[str, str]):
        self.km, self.minutes, self.names = km, minutes, names
        self.weeks = 0
        self.lists: dict[str, list[float]] = defaultdict(list)
        self.counts: dict[str, Counter] = defaultdict(Counter)
        self.points: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self.arrivals = [0] * (7 * 24)
        self.ratio_bins: dict[str, Counter] = defaultdict(Counter)
        # Opening fee / typical fee bin -> gigs, gigs booked, bookings, drops and minutes to the first booking
        self.fee_bins: dict[str, dict] = defaultdict(
            lambda: {"gigs": 0, "booked": 0, "bookings": 0, "drops": 0, "minutes": []}
        )
        self.posted_hours, self.booked_by_posted_hour = Counter(), Counter()
        self.priced: list[dict] = []  # each request's km and drive minutes per leg, prices and features

    def add(self, week: Week) -> None:
        self.weeks += 1
        events, kinds = week.events, Counter(e["kind"] for e in week.events)
        for kind, n in kinds.items():
            self.lists[f"perWeek.{kind}"].append(n)
        requests = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
        self.add_requests(list(requests.values()))
        self.add_quotes(week.reveal.get("requests", []))
        self.add_orders(week, requests)
        self.add_gigs(week, requests)
        self.add_drivers(week.drivers)
        for e in events:
            if e["kind"] == "forecast":
                self.lists["forecast.hours"].append((e["to"] - e["from"]) / HOUR)
                self.lists["forecast.places"].append(len(e["placeIds"]))
                self.counts["forecast.startDay"][(e["from"] // DAY) % 7] += 1
            elif e["kind"] == "ledger":
                self.counts["ledger.count"][e["line"]["kind"]] += 1
                self.counts["ledger.cents"][e["line"]["kind"]] += e["line"]["cents"]
        score = week.meta.get("score") or {}
        for key in ("marginCents", "revenueCents", "wonOrders", "onTimeShare", "undeliveredShare"):
            if key in score:
                self.lists[f"score.{key}"].append(score[key])

    def add_requests(self, requests: list[dict]) -> None:
        self.lists["requests.perWeek"].append(len(requests))
        batches, dealers = Counter(), Counter()
        for r in requests:
            self.arrivals[min(r["arrivedAt"] // HOUR, len(self.arrivals) - 1)] += 1
            self.lists["requests.answerMinutes"].append(r["respondBy"] - r["arrivedAt"])
            self.counts["requests.legs"][len(r["legs"])] += 1
            self.counts["requests.options"]["+".join(o["kind"] for o in r["options"])] += 1
            self.counts["requests.note"][r["note"]["language"] if r["note"] else "none"] += 1
            dealers[r["dealerId"]] += 1
            if r["batchId"]:
                batches[r["batchId"]] += 1
            km = sum(self.km.get((leg["pickup"]["placeId"], leg["delivery"]["placeId"]), 0) for leg in r["legs"])
            drive = sum(
                self.minutes.get((leg["pickup"]["placeId"], leg["delivery"]["placeId"]), 0) for leg in r["legs"]
            )
            legs = len(r["legs"])
            self.priced.append(self.price_row(r))
            self.points[f"referenceFee~driveMinutes.legs{legs}"].append((drive, r["referenceFeeCents"]))
            for option in r["options"]:
                self.points[f"listPrice~km.{option['kind']}.legs{legs}"].append((km, option["listPriceCents"]))
                self.lists[f"requests.feeOverList.{option['kind']}"].append(
                    r["referenceFeeCents"] / option["listPriceCents"]
                )
                self.lists[f"requests.deadlineAfterArrivalHours.{option['kind']}"].append(
                    (option["deadline"] - r["arrivedAt"]) / HOUR
                )
            for leg in r["legs"]:
                car, pickup, delivery = leg["car"], leg["pickup"], leg["delivery"]
                self.counts["legs.car"]["premium" if car["premium"] else "standard"] += 1
                self.counts["legs.electric"][car["electric"]] += 1
                if car["electric"] and car["chargePercent"] is not None:
                    self.lists["legs.chargePercent"].append(car["chargePercent"])
                self.counts["legs.privatePickup"][pickup["privateAddress"]] += 1
                self.counts["legs.privateDelivery"][delivery["privateAddress"]] += 1
                self.counts["legs.pickupPlace"][self.names.get(pickup["placeId"], pickup["placeId"])] += 1
                self.counts["legs.deliveryPlace"][self.names.get(delivery["placeId"], delivery["placeId"])] += 1
                self.counts["legs.lane"][f"{pickup['placeId']}>{delivery['placeId']}"] += 1
                self.lists["legs.readyAfterArrivalHours"].append((pickup["window"]["from"] - r["arrivedAt"]) / HOUR)
                self.lists["legs.km"].append(self.km.get((pickup["placeId"], delivery["placeId"]), 0))
                if pickup["privateAddress"]:
                    self.lists["legs.privatePickupSlotHours"].append(
                        (pickup["window"]["to"] - pickup["window"]["from"]) / HOUR
                    )
        self.lists["requests.dealersPerWeek"].append(len(dealers))
        self.lists["requests.perDealer"].extend(dealers.values())
        self.lists["requests.batchSize"].extend(batches.values())

    def price_row(self, r: dict) -> dict:
        """What priceOverFit needs of a request: km and drive minutes of each leg, its prices, and its features."""
        lanes = [(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in r["legs"]]
        cars = [leg["car"] for leg in r["legs"]]
        car = (
            "premium"
            if any(c["premium"] for c in cars)
            else "electric"
            if any(c["electric"] for c in cars)
            else "standard"
        )
        private = any(leg[end]["privateAddress"] for leg in r["legs"] for end in ("pickup", "delivery"))
        return {
            "km": [self.km.get(lane, 0) for lane in lanes],
            "minutes": [self.minutes.get(lane, 0) for lane in lanes],
            "listPrices": {o["kind"]: o["listPriceCents"] for o in r["options"]},
            "typicalFee": r["referenceFeeCents"],
            "features": {
                "note": r["note"]["language"] if r["note"] else "none",
                "car": car,
                "legs": len(r["legs"]),
                "privateAddress": private,
            },
        }

    def add_quotes(self, revealed: list[dict]) -> None:
        """How dealers answer prices: for each quoted option, quote / list price, and whether the dealer took it."""
        for r in revealed:
            self.counts["quotes.outcome"][r["outcome"]] += 1
            if not r["quote"]:
                continue
            day = (r["request"]["arrivedAt"] // DAY) % 7
            lists = {o["kind"]: o["listPriceCents"] for o in r["request"]["options"]}
            ratios = {k: p / lists[k] for k, p in r["quote"].items() if lists.get(k)}
            for kind, ratio in ratios.items():
                bin_ = f"{math.floor(ratio / RATIO_BIN) * RATIO_BIN:.2f}"
                taken = r["outcome"] == "won" and r["option"] == kind
                self.ratio_bins[f"option.{kind}.quoted"][bin_] += 1
                self.ratio_bins[f"option.{kind}.taken"][bin_] += taken
            if ratios:
                bin_ = f"{math.floor(min(ratios.values()) / RATIO_BIN) * RATIO_BIN:.2f}"
                self.ratio_bins["request.quoted"][bin_] += 1
                self.ratio_bins["request.won"][bin_] += r["outcome"] == "won"
                self.counts["quotes.wonByDay"][day] += r["outcome"] == "won"
                self.counts["quotes.quotedByDay"][day] += 1
            if r["outcome"] == "won":
                self.counts["quotes.optionTaken"][f"{len(ratios)} quoted: {r['option']}"] += 1

    def add_orders(self, week: Week, requests: dict[str, dict]) -> None:
        orders = week.snapshot.get("orders", [])
        if not orders:
            return
        kinds = Counter(e["kind"] for e in week.events)
        won = len(orders)
        for kind in ("order_changed", "order_cancelled", "deadline_close", "visit_failed", "release"):
            self.lists[f"orders.{kind}PerOrder"].append(kinds[kind] / won)
        for e in week.events:
            if e["kind"] == "visit_failed":
                self.counts["orders.visitFailedReason"][e["reason"]] += 1
            elif e["kind"] == "order_cancelled":
                for gig in e["gigs"]:
                    self.counts["orders.cancelledGigOutcome"][gig["outcome"]] += 1
        for order in orders:
            self.counts["orders.status"][order["status"]] += 1
            self.counts["orders.option"][order["option"]] += 1
            if order["status"] == "cancelled":
                continue
            done = [t for t in order["deliveredAt"] if t is not None]
            if len(done) < len(order["legs"]):
                self.counts["orders.onTime"]["undelivered"] += 1
                continue
            late = max(done) - order["deadline"]
            self.counts["orders.onTime"]["late" if late > 0 else "on time"] += 1
            if late > 0:
                self.lists["orders.lateHours"].append(late / HOUR)
            request = requests.get(order["id"])
            if request:
                promised = next((o["deadline"] for o in request["options"] if o["kind"] == order["option"]), None)
                if promised is not None:
                    self.lists["orders.deadlineMovedHours"].append((order["deadline"] - promised) / HOUR)
        for truth in week.reveal.get("orders", []):
            request = requests.get(truth["orderId"])
            for i, leg in enumerate(truth["legs"]):
                for flag in ("manualGearbox", "needsPlates", "summerTyres"):
                    self.counts[f"truth.{flag}"][leg[flag]] += 1
                self.counts["truth.releasedAfterPayment"][leg["releasedAt"] is not None] += 1
                self.counts["truth.noteDeadline"][leg["noteDeadline"] is not None] += 1
                if request:
                    stated = request["legs"][i]["pickup"]
                    self.lists["truth.readyDelayHours"].append((leg["readyAt"] - stated["window"]["from"]) / HOUR)
                    self.counts["truth.realPickupHoursDiffer"][
                        leg["pickupHours"] is not None and leg["pickupHours"] != stated["hours"]
                    ] += 1
                if leg["pickedUpAt"] is not None and leg["deliveredAt"] is not None:
                    self.lists["truth.driveMinutes"].append(leg["deliveredAt"] - leg["pickedUpAt"])

    def add_gigs(self, week: Week, requests: dict[str, dict]) -> None:
        """How drivers answer gigs: views, bookings and their fees, drops, no-shows and late drivers."""
        gigs = {g["id"]: g for g in week.snapshot.get("gigs", [])}
        if not gigs:
            return
        first_view: dict[str, int] = {}
        views: Counter = Counter()
        viewers: dict[str, set] = defaultdict(set)
        booked: dict[str, dict] = {}
        last_booked: dict[str, int] = {}
        bookings: Counter = Counter()
        drops: Counter = Counter()
        kinds: Counter = Counter()
        for e in week.events:
            if "gigId" not in e or e["gigId"] not in gigs:
                continue
            kinds[e["kind"]] += 1
            if e["kind"] == "gig_viewed":
                first_view.setdefault(e["gigId"], e["at"])
                views[e["gigId"]] += 1
                viewers[e["gigId"]].add(e["driverId"])
            elif e["kind"] == "gig_booked":
                booked.setdefault(e["gigId"], e)
                last_booked[e["gigId"]] = e["at"]
                bookings[e["gigId"]] += 1
            elif e["kind"] == "gig_dropped":
                drops[e["gigId"]] += 1
                if e["gigId"] in last_booked:
                    self.lists["gigs.minutesFromBookingToDrop"].append(e["at"] - last_booked[e["gigId"]])
            elif e["kind"] == "offer_answered":
                self.counts["gigs.offerAnswer"][e["answer"]] += 1
        self.counts["gigs.status"].update(g["status"] for g in gigs.values())
        for kind in ("gig_dropped", "no_show", "driver_late", "gig_started"):
            self.lists[f"gigs.{kind}PerBooking"].append(kinds[kind] / (kinds["gig_booked"] or 1))
        self.lists["gigs.expiredPerGig"].append(kinds["gig_expired"] / len(gigs))
        self.lists["gigs.bookedShare"].append(len(booked) / len(gigs))
        for gig_id, gig in gigs.items():
            self.lists["gigs.views"].append(views[gig_id])
            self.lists["gigs.distinctViewers"].append(len(viewers[gig_id]))
            if gig_id in first_view:
                self.lists["gigs.minutesToFirstView"].append(first_view[gig_id] - gig["postedAt"])
            cars = sum(1 for s in gig["stops"] if s["kind"] == "pickup")
            self.counts["gigs.cars"][cars] += 1
            request = requests.get(gig["stops"][0]["orderId"])
            reference = request["referenceFeeCents"] * cars / len(request["legs"]) if request else None
            opening = gig["schedule"][0]["feeCents"]
            booking = booked.get(gig_id)
            hour = (gig["postedAt"] % DAY) // HOUR
            self.posted_hours[hour] += 1
            self.booked_by_posted_hour[hour] += booking is not None
            if reference:
                self.lists["gigs.openingFeeOverReference"].append(opening / reference)
                # The tolerance keeps a fee rounded to the cent, such as exactly the typical fee, in its own bin
                fee_bin = self.fee_bins[f"{math.floor(opening / reference / FEE_BIN + 1e-3) * FEE_BIN:.1f}"]
                fee_bin["gigs"] += 1
                fee_bin["booked"] += booking is not None
                fee_bin["bookings"] += bookings[gig_id]
                fee_bin["drops"] += drops[gig_id]
                if booking is not None:
                    fee_bin["minutes"].append(booking["at"] - gig["postedAt"])
            if booking is None:
                continue
            self.lists["gigs.minutesToBooking"].append(booking["at"] - gig["postedAt"])
            self.lists["gigs.bookedFeeOverOpening"].append(booking["feeCents"] / opening)
            self.counts["gigs.bookedHourOfDay"][(booking["at"] % DAY) // HOUR] += 1
            if reference:
                self.lists["gigs.bookedFeeOverReference"].append(booking["feeCents"] / reference)
                self.points["bookedFee~reference"].append((reference, booking["feeCents"]))
            if request:
                pickup = request["legs"][gig["stops"][0]["leg"]]["pickup"]["window"]["from"]
                self.lists["gigs.bookedHoursBeforeReady"].append((pickup - booking["at"]) / HOUR)

    def add_drivers(self, drivers: list[dict]) -> None:
        if not drivers:
            return
        self.lists["drivers.perWeek"].append(len(drivers))
        homes = Counter(self.names.get(d["homePlaceId"], d["homePlaceId"]) for d in drivers)
        for place, n in homes.items():
            self.lists[f"drivers.homeShare.{place}"].append(n / len(drivers))
        self.counts["drivers.licence"].update(d["licence"] for d in drivers)
        self.lists["drivers.rating"].extend(d["rating"] for d in drivers)
        self.lists["drivers.completedGigs"].extend(d["completedGigs"] for d in drivers)
        self.lists["drivers.dropShare"].extend(d["drops"] / d["completedGigs"] for d in drivers if d["completedGigs"])
        self.lists["drivers.experiencedShare"].append(
            sum(1 for d in drivers if d["rating"] >= 4.8 and d["completedGigs"] >= 50) / len(drivers)
        )

    def fee_response(self) -> dict:
        """For bins of opening fee / typical fee: gigs, the share booked, minutes to booking and drops per booking."""
        return {
            b: {
                "n": v["gigs"],
                "bookedShare": round(v["booked"] / v["gigs"], 4),
                "minutesToBooking": quantiles(v["minutes"]),
                "dropsPerBooking": round(v["drops"] / v["bookings"], 4) if v["bookings"] else None,
            }
            for b, v in sorted(self.fee_bins.items(), key=lambda kv: float(kv[0]))
        }

    def price_over_fit(self) -> dict:
        """Each request's list prices and typical fee over what the one-car line predicts for its legs (km for list
        prices, drive minutes for the typical fee, summed over the legs), split by feature."""
        prices = {
            f"listPrice.{kind}": ("km", lambda r, kind=kind: r["listPrices"].get(kind))
            for kind in sorted({kind for r in self.priced for kind in r["listPrices"]})
        }
        prices["typicalFee"] = ("minutes", lambda r: r["typicalFee"])
        out = {}
        for name, (x, price) in prices.items():
            one_car = [(r[x][0], price(r)) for r in self.priced if len(r[x]) == 1 and r[x][0] and price(r)]
            fit = fit_line(one_car)
            if "slope" not in fit:
                continue
            ratios: list[float] = []
            split: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
            for r in self.priced:
                predicted = sum(fit["intercept"] + fit["slope"] * v for v in r[x])
                if not price(r) or not all(r[x]) or predicted <= 0:
                    continue
                ratios.append(price(r) / predicted)
                for feature, value in r["features"].items():
                    split[feature][str(value)].append(ratios[-1])
            out[name] = {"all": quantiles(ratios)} | {
                feature: {v: quantiles(xs) for v, xs in sorted(values.items())} for feature, values in split.items()
            }
        return out

    def summary(self) -> dict:
        lists = {k: quantiles(v) for k, v in sorted(self.lists.items()) if not k.startswith("drivers.homeShare.")}
        home = {
            k.removeprefix("drivers.homeShare."): round(sum(v) / self.weeks, 4)
            for k, v in self.lists.items()
            if k.startswith("drivers.homeShare.")
        }
        counts = {k: shares(v) for k, v in sorted(self.counts.items()) if not k.startswith(("ledger.", "legs.lane"))}
        counts["gigs.bookedShareByPostHour"] = {
            str(h): {"count": n, "share": round(self.booked_by_posted_hour[h] / n, 4)}
            for h, n in sorted(self.posted_hours.items())
        }
        counts["legs.lane.top30"] = shares(
            Counter(dict(self.counts["legs.lane"].most_common(30))), sum(self.counts["legs.lane"].values())
        )
        ledger = {
            kind: {
                "perWeek": round(n / self.weeks, 2),
                "eurosPerWeek": round(self.counts["ledger.cents"][kind] / 100 / self.weeks, 2),
            }
            for kind, n in self.counts["ledger.count"].items()
        }
        response = {}
        for key in sorted(k for k in self.ratio_bins if k.endswith((".quoted",))):
            hit = self.ratio_bins[key.removesuffix(".quoted") + (".won" if key.startswith("request") else ".taken")]
            response[key.removesuffix(".quoted")] = {
                b: {"n": n, "rate": round(hit[b] / n, 4)}
                for b, n in sorted(self.ratio_bins[key].items(), key=lambda kv: float(kv[0]))
            }
        return {
            "weeks": self.weeks,
            "arrivalsPerHourOfWeek": [round(n / self.weeks, 3) for n in self.arrivals],
            "numbers": lists,
            "counts": counts,
            "fits": {k: fit_line(v) for k, v in sorted(self.points.items())},
            "quoteResponse": response,
            "feeResponse": self.fee_response(),
            "priceOverFit": self.price_over_fit(),
            "driverHomeShare": dict(sorted(home.items(), key=lambda kv: -kv[1])),
            "ledger": ledger,
        }


def summarise(weeks: Iterable[Week], world_map: dict | None) -> dict:
    """The summary of all weeks: the event catalogue, and the statistics of each level and policy."""
    roads = world_map["roads"] if world_map else []
    km = {(r["from"], r["to"]): r["km"] for r in roads}
    minutes = {(r["from"], r["to"]): r["minutes"] for r in roads}
    names = {p["id"]: p["name"] for p in world_map["places"]} if world_map else {}
    catalogue, groups = Catalogue(), {}
    for week in weeks:
        tag = week.meta.get("tag")
        name = f"L{week.meta['level']}/{week.meta['policy']}" + (f"-{tag}" if tag else "")
        group = groups.setdefault(name, Group(km, minutes, names))
        group.add(week)
        for event in week.events:
            catalogue.add(name, event)
    return {
        "groups": {name: groups[name].summary() for name in sorted(groups)},
        "eventCatalogue": catalogue.summary(),
    }


def report(summary: dict) -> str:
    """The main numbers as text."""
    lines = []
    for name, g in summary["groups"].items():
        n = g["numbers"]

        def mean(key: str, scale: float = 1, n: dict = n) -> str:
            return f"{n[key]['mean'] * scale:.2f}" if n.get(key, {}).get("n") else "-"

        lines.append(f"== {name}: {g['weeks']} weeks")
        lines.append(
            f"  requests/week {mean('requests.perWeek')}, drivers/week {mean('drivers.perWeek')}, "
            f"forecasts/week {mean('perWeek.forecast')}"
        )
        if n.get("score.wonOrders", {}).get("mean"):
            lines.append(
                f"  margin/week €{mean('score.marginCents', 0.01)}, orders {mean('score.wonOrders')}, "
                f"on time {mean('score.onTimeShare', 100)}%"
            )
        if n.get("gigs.bookedShare", {}).get("n"):
            lines.append(
                f"  gigs booked {mean('gigs.bookedShare', 100)}%, minutes to booking p50 "
                f"{n['gigs.minutesToBooking'].get('p50', '-')}, booked fee / typical fee p50 "
                f"{n.get('gigs.bookedFeeOverReference', {}).get('p50', '-')}, drops/booking "
                f"{mean('gigs.gig_droppedPerBooking')}"
            )
        for key, bins in g["quoteResponse"].items():
            if key.startswith("request"):
                curve = ", ".join(f"{b}:{v['rate']:.0%}" for b, v in bins.items() if v["n"] >= 5)
                lines.append(f"  win rate by lowest quote / list price: {curve}")
        curve = ", ".join(f"{b}:{v['bookedShare']:.0%}" for b, v in g["feeResponse"].items() if v["n"] >= 5)
        if curve:
            lines.append(f"  booked share by opening fee / typical fee: {curve}")
    lines.append("== event kinds: " + ", ".join(f"{k} {v['count']}" for k, v in summary["eventCatalogue"].items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Summarises weeks saved by scrape.py.")
    parser.add_argument(
        "folders", nargs="*", type=Path, help="scrape output folders (default: the committed data/scrape)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="where to write summary.json (default: the first folder, or out/summary.json for data/scrape)",
    )
    args = parser.parse_args(argv)
    roots = args.folders or [OFFLINE_DATA]
    folders = list(find_weeks(roots))
    if not folders:
        raise SystemExit("No saved weeks (folders with meta.json) found.")
    summary = summarise((load_week(f) for f in folders), load_map(roots))
    out = args.out or (args.folders[0] / "summary.json" if args.folders else Path("out/summary.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(report(summary))
    print(f"{len(folders)} weeks summarised into {out}")


if __name__ == "__main__":
    main()
