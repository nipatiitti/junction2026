"""Fast tests for admission control, on a hand-made map of three towns. No network."""

from strategies.admission import Admission, Held, Params

HOUR, DAY = 60, 24 * 60
TUESDAY_9 = DAY + 9 * HOUR

# Three towns: Isokylä and Pikkukylä are 30 minutes apart, Erämaa is five hours from both.
TOWNS = ["isokyla", "pikkukyla", "eramaa"]
MINUTES = {("isokyla", "pikkukyla"): 30, ("isokyla", "eramaa"): 300, ("pikkukyla", "eramaa"): 300}


def world_map() -> dict:
    roads = []
    for a in TOWNS:
        for b in TOWNS:
            minutes = 15 if a == b else MINUTES.get((a, b)) or MINUTES[(b, a)]
            roads.append({"from": a, "to": b, "km": minutes, "minutes": minutes})
    return {"places": [{"id": t, "name": t, "lat": 0.0, "lon": 0.0} for t in TOWNS], "roads": roads}


def roster(count: int = 40) -> list[dict]:
    """Every driver lives in Isokylä; nobody lives in Erämaa."""
    return [
        {
            "id": f"d{i}",
            "homePlaceId": "isokyla",
            "rating": 4.9,
            "licence": "manual",
            "completedGigs": 80,
            "drops": 0,
        }
        for i in range(count)
    ]


def request(rid: str, pickup: str, delivery: str, ready: int = TUESDAY_9, fee: int = 10000) -> dict:
    deadline = ready // DAY * DAY + 20 * HOUR
    return {
        "id": rid,
        "dealerId": "dealer-1",
        "batchId": None,
        "arrivedAt": ready - HOUR,
        "respondBy": ready - 45,
        "legs": [
            {
                "car": {"premium": False, "electric": False, "chargePercent": None},
                "pickup": {
                    "placeId": pickup,
                    "privateAddress": False,
                    "window": {"from": ready, "to": deadline},
                    "hours": None,
                },
                "delivery": {
                    "placeId": delivery,
                    "privateAddress": False,
                    "window": {"from": ready, "to": deadline},
                    "hours": None,
                },
            }
        ],
        "options": [
            {"kind": "same_day", "deadline": deadline, "listPriceCents": 2 * fee},
            {"kind": "next_day", "deadline": deadline + DAY, "listPriceCents": 2 * fee},
        ],
        "referenceFeeCents": fee,
        "note": None,
    }


def order_from(req: dict, oid: str) -> dict:
    return {
        "id": oid,
        "dealerId": req["dealerId"],
        "option": "same_day",
        "priceCents": req["options"][0]["listPriceCents"],
        "deadline": req["options"][0]["deadline"],
        "legs": req["legs"],
        "status": "waiting",
        "deliveredAt": [None] * len(req["legs"]),
        "lastPickupAt": req["options"][0]["deadline"] - 3 * HOUR,
    }


def admission(**params) -> Admission:
    return Admission(roster(), world_map(), level=8, params=Params(**params))


def test_a_request_from_a_town_without_drivers_is_declined():
    verdict = admission().assess(request("R1", "eramaa", "isokyla"))
    assert not verdict.accept
    assert verdict.options == []


def test_a_request_from_a_town_with_many_drivers_is_accepted():
    verdict = admission().assess(request("R1", "isokyla", "pikkukyla"))
    assert verdict.accept
    assert verdict.options and verdict.expected_cost > 0


def test_a_full_area_declines_more_cars():
    adm = admission(capacity_per_driver=0.05)  # 40 drivers nearby: room for 2 cars that wait for a driver
    held = [Held(order_from(request(f"O{i}", "isokyla", "pikkukyla"), f"O{i}"), booked=False) for i in range(2)]
    assert not adm.assess(request("R1", "isokyla", "pikkukyla"), held).accept
    booked = [h._replace(booked=True) for h in held]  # once drivers hold them, the area has room again
    assert adm.assess(request("R2", "isokyla", "pikkukyla"), booked).accept


def test_acceptance_tightens_when_the_on_time_share_nears_the_minimum():
    adm = admission(capacity_per_driver=0.2)  # room for 5 waiting cars while we are on time
    held = [Held(order_from(request(f"O{i}", "isokyla", "pikkukyla"), f"O{i}"), booked=False) for i in range(2)]
    assert adm.assess(request("R1", "isokyla", "pikkukyla"), held).accept

    adm.on_time, adm.late = 44, 6  # 88% on time, under the 90% minimum
    assert adm.tightening(adm.on_time_share()) < 0.5
    assert not adm.assess(request("R2", "isokyla", "pikkukyla"), held).accept


def test_a_late_order_counts_against_the_share_once_its_deadline_passes():
    adm = admission()
    order = order_from(request("O1", "isokyla", "pikkukyla"), "O1")
    adm.observe({"kind": "order_won", "at": TUESDAY_9 - 45, "order": order})
    adm.observe({"kind": "ledger", "at": order["deadline"] + 1})
    assert (adm.on_time, adm.late) == (0, 1)


def test_a_return_leg_scores_better_than_the_same_request_alone():
    out = request("O1", "isokyla", "pikkukyla")
    back = request("R1", "pikkukyla", "isokyla")
    alone = admission().assess(back)
    paired = admission().assess(back, [Held(order_from(out, "O1"), booked=True)])
    assert paired.accept
    assert paired.expected_cost < alone.expected_cost
    assert paired.score > alone.score


def test_the_latest_option_is_quoted_when_the_first_leaves_too_little_time():
    late_in_the_day = request("R1", "isokyla", "pikkukyla", ready=DAY + 15 * HOUR)
    verdict = admission().assess(late_in_the_day)
    assert verdict.options == ["next_day"]


def test_a_request_that_costs_more_than_its_price_is_declined():
    req = request("R1", "isokyla", "pikkukyla")
    for option in req["options"]:
        option["listPriceCents"] = req["referenceFeeCents"]  # the price only just pays the typical fee
    assert not admission().assess(req).accept
    assert admission(price_factor=2.0).assess(req).accept


def test_drops_lower_the_supply_of_a_town():
    adm = admission()
    before = adm.supply("isokyla")
    for i in range(5):
        adm.observe({"kind": "gig_dropped", "at": TUESDAY_9, "gigId": f"g{i}", "driverId": f"d{i}"})
    assert adm.supply("isokyla") < before
