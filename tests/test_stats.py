"""Fast tests without network: stats.py on a small synthetic week."""

import gzip
import json

from stats import Week, find_weeks, load_week, quantiles, summarise

WORLD_MAP = {
    "places": [{"id": "a", "name": "Aa", "lat": 0, "lon": 0}, {"id": "b", "name": "Bb", "lat": 0, "lon": 1}],
    "roads": [
        {"from": "a", "to": "b", "km": 100, "minutes": 60},
        {"from": "b", "to": "a", "km": 100, "minutes": 60},
        {"from": "a", "to": "a", "km": 20, "minutes": 20},
    ],
}
HOURS = {"opens": 480, "closes": 1080, "weekdays": [0, 1, 2, 3, 4], "saturday": None}


def request(rid: str, arrived: int, to: str, list_cents: int, note=None) -> dict:
    stop = {"privateAddress": False, "window": {"from": arrived, "to": 1200}, "hours": HOURS}
    return {
        "id": rid,
        "dealerId": "D01",
        "batchId": None,
        "arrivedAt": arrived,
        "respondBy": arrived + 15,
        "legs": [
            {
                "car": {"premium": False, "electric": False, "chargePercent": None},
                "pickup": {**stop, "placeId": "a"},
                "delivery": {**stop, "placeId": to},
            }
        ],
        "options": [{"kind": "next_day", "deadline": 2640, "listPriceCents": list_cents}],
        "referenceFeeCents": 3000,
        "note": note,
    }


def synthetic_week() -> Week:
    r1 = request("R1", 540, "b", 4500, {"text": "Nouto ennen klo 14", "language": "fi"})  # 100 km
    r2 = request("R2", 600, "a", 2500)  # 20 km
    order = {
        "id": "R1",
        "dealerId": "D01",
        "option": "next_day",
        "priceCents": 4500,
        "deadline": 2640,
        "legs": r1["legs"],
        "status": "delivered",
        "deliveredAt": [900],
        "lastPickupAt": 1000,
    }
    gig = {
        "id": "g1",
        "stops": [{"orderId": "R1", "leg": 0, "kind": "pickup"}, {"orderId": "R1", "leg": 0, "kind": "delivery"}],
        "audience": {"experienced": False, "manualLicence": False},
        "schedule": [{"at": 560, "feeCents": 3000}],
        "status": "done",
        "postedAt": 560,
        "feeCents": 3300,
        "driverId": "d1",
    }
    events = [
        {"seq": 0, "at": 540, "kind": "price_request", "request": r1},
        {"seq": 1, "at": 555, "kind": "order_won", "order": order},
        {"seq": 2, "at": 565, "kind": "gig_viewed", "gigId": "g1", "driverId": "d1"},
        {"seq": 3, "at": 570, "kind": "gig_viewed", "gigId": "g1", "driverId": "d2"},
        {"seq": 4, "at": 580, "kind": "gig_booked", "gigId": "g1", "driverId": "d1", "feeCents": 3300},
        {"seq": 5, "at": 600, "kind": "price_request", "request": r2},
        {"seq": 6, "at": 615, "kind": "order_lost", "requestId": "R2"},
        {"seq": 7, "at": 900, "kind": "delivered", "gigId": "g1", "orderId": "R1", "leg": 0, "placeId": "b"},
        {
            "seq": 8,
            "at": 900,
            "kind": "ledger",
            "line": {"at": 900, "kind": "revenue", "cents": 4500, "orderId": "R1", "gigId": None, "detail": "R1"},
        },
    ]
    reveal = {
        "requests": [
            {"request": r1, "quote": {"next_day": 4500}, "outcome": "won", "option": "next_day"},
            {"request": r2, "quote": {"next_day": 5000}, "outcome": "lost", "option": None},
        ],
        "orders": [],
        "views": [],
    }
    drivers = [
        {"id": "d1", "homePlaceId": "a", "rating": 4.9, "licence": "manual", "completedGigs": 60, "drops": 3},
        {"id": "d2", "homePlaceId": "b", "rating": 4.5, "licence": "automatic_only", "completedGigs": 10, "drops": 0},
    ]
    meta = {"seed": "t-1", "level": 8, "policy": "explore", "score": {"marginCents": 1200, "wonOrders": 1}}
    return Week(meta, events, reveal, {"orders": [order], "gigs": [gig]}, drivers)


def test_quantiles_of_a_list():
    q = quantiles([1, 2, 3, 4, 5])
    assert (q["n"], q["mean"], q["min"], q["p50"], q["max"]) == (5, 3, 1, 3, 5)
    assert quantiles([]) == {"n": 0}


def test_catalogue_lists_every_kind_with_its_fields_and_enumerations():
    catalogue = summarise([synthetic_week()], WORLD_MAP)["eventCatalogue"]
    assert set(catalogue) == {
        "price_request",
        "order_won",
        "gig_viewed",
        "gig_booked",
        "order_lost",
        "delivered",
        "ledger",
    }
    assert catalogue["price_request"]["count"] == 2
    assert catalogue["price_request"]["fields"]["request.legs[].pickup.privateAddress"] == {"bool": 2}
    assert catalogue["price_request"]["enumerations"]["request.note.language"] == {"fi": 1}
    assert catalogue["ledger"]["enumerations"]["line.kind"] == {"revenue": 1}
    # Ids and free text are not enumerations.
    assert "request.id" not in catalogue["price_request"]["enumerations"]
    assert "line.detail" not in catalogue["ledger"]["enumerations"]
    assert catalogue["gig_booked"]["range"]["feeCents"] == [3300, 3300]


def test_request_distributions_and_list_price_against_distance():
    group = summarise([synthetic_week()], WORLD_MAP)["groups"]["L8/explore"]
    assert group["weeks"] == 1
    assert group["numbers"]["requests.perWeek"]["mean"] == 2
    assert group["counts"]["requests.note"] == {"none": {"count": 1, "share": 0.5}, "fi": {"count": 1, "share": 0.5}}
    assert group["arrivalsPerHourOfWeek"][9] == 1 and group["arrivalsPerHourOfWeek"][10] == 1
    fit = group["fits"]["listPrice~km.next_day.legs1"]
    assert (fit["intercept"], fit["slope"]) == (2000, 25)  # 4500 at 100 km, 2500 at 20 km
    assert group["driverHomeShare"] == {"Aa": 0.5, "Bb": 0.5}


def test_quote_response_bins_by_quote_over_list_price():
    response = summarise([synthetic_week()], WORLD_MAP)["groups"]["L8/explore"]["quoteResponse"]
    assert response["request"] == {"1.00": {"n": 1, "rate": 1.0}, "2.00": {"n": 1, "rate": 0.0}}
    assert response["option.next_day"]["1.00"] == {"n": 1, "rate": 1.0}


def test_gig_timings_and_fees():
    numbers = summarise([synthetic_week()], WORLD_MAP)["groups"]["L8/explore"]["numbers"]
    assert numbers["gigs.minutesToFirstView"]["mean"] == 5
    assert numbers["gigs.minutesToBooking"]["mean"] == 20
    assert numbers["gigs.bookedFeeOverReference"]["mean"] == 1.1
    assert numbers["gigs.distinctViewers"]["mean"] == 2


def test_weeks_load_from_the_folders_that_scrape_writes(tmp_path):
    week = synthetic_week()
    folder = tmp_path / "L8" / "t-1"
    folder.mkdir(parents=True)
    with gzip.open(folder / "events.jsonl.gz", "wt") as f:
        f.writelines(json.dumps(e) + "\n" for e in week.events)
    for name, data in (("reveal", week.reveal), ("snapshot", week.snapshot), ("drivers", week.drivers)):
        with gzip.open(folder / f"{name}.json.gz", "wt") as f:
            json.dump(data, f)
    (folder / "meta.json").write_text(json.dumps(week.meta))
    (tmp_path / "L8" / "t-2.partial").mkdir()  # an unfinished week is skipped
    (tmp_path / "L8" / "t-2.partial" / "meta.json").write_text("{}")
    assert list(find_weeks([tmp_path])) == [folder]
    assert load_week(folder) == week
