"""Fast tests for direct offers, on a hand-made map of three towns. No network."""

from strategies.offers import GigInfo, Offers
from strategies.offers.offers import PER_DRIVER_PER_DAY, PER_GIG_OPEN

HOUR, DAY = 60, 24 * 60
TUESDAY_10 = DAY + 10 * HOUR

# Satama and Asema are 20 minutes apart; Kaukola is four hours from both.
TOWNS = ["satama", "asema", "kaukola"]
MINUTES = {("satama", "asema"): 20, ("satama", "kaukola"): 240, ("asema", "kaukola"): 240}


def world_map() -> dict:
    roads = []
    for a in TOWNS:
        for b in TOWNS:
            minutes = 10 if a == b else MINUTES.get((a, b)) or MINUTES[(b, a)]
            roads.append({"from": a, "to": b, "km": minutes, "minutes": minutes})
    return {"places": [{"id": t, "name": t, "lat": 0.0, "lon": 0.0} for t in TOWNS], "roads": roads}


def driver(did: str, home: str, licence: str = "manual", rating: float = 4.9, gigs: int = 80) -> dict:
    return {"id": did, "homePlaceId": home, "rating": rating, "licence": licence, "completedGigs": gigs, "drops": 0}


def gig(
    pickup: str = "asema", manual: bool = False, experienced: bool = False, until: int = DAY + 18 * HOUR
) -> GigInfo:
    return GigInfo(
        pickup=pickup,
        pickup_until=until,
        end="kaukola",
        drive=240,
        manual=manual,
        experienced=experienced,
    )


SCHEDULE = [{"at": DAY, "feeCents": 10000}]


def offers_with(roster: list[dict], *gigs: tuple[str, GigInfo]) -> Offers:
    o = Offers(roster, world_map(), level=8)
    for gig_id, info in gigs:
        o.register(gig_id, info, SCHEDULE)
    return o


def finishes(o: Offers, driver_id: str, place: str, at: int) -> None:
    """A driver of ours delivers the last car of a gig at `place`."""
    o.register("done-" + driver_id, gig()._replace(end=place), SCHEDULE)
    o.observe({"kind": "gig_booked", "at": at - 2 * HOUR, "gigId": "done-" + driver_id, "driverId": driver_id})
    o.observe({"kind": "delivered", "at": at, "gigId": "done-" + driver_id, "placeId": place, "orderId": "O", "leg": 0})


def test_a_driver_finishing_near_the_pickup_is_chosen_before_one_living_far_away():
    o = offers_with([driver("near", "kaukola"), driver("far", "kaukola")], ("g1", gig()))
    finishes(o, "near", "satama", TUESDAY_10 - 30)
    sent = o.offers("g1", TUESDAY_10, rescue=True)
    assert [a["driverId"] for a in sent] == ["near"]
    assert sent[0]["feeCents"] == 10000  # a rescue goes at the app fee


def test_a_chain_offer_goes_below_the_app_fee():
    o = offers_with([driver("near", "kaukola")], ("g1", gig()))
    finishes(o, "near", "asema", TUESDAY_10 - 30)
    (sent,) = o.due(TUESDAY_10)
    assert sent["driverId"] == "near" and sent["feeCents"] < 10000


def test_a_rescue_reaches_drivers_who_live_near_the_pickup():
    o = offers_with([driver("local", "asema"), driver("far", "kaukola")], ("g1", gig()))
    assert [a["driverId"] for a in o.offers("g1", TUESDAY_10, rescue=True)] == ["local"]
    assert o.offers("g1", TUESDAY_10 + 15, rescue=False) == []  # no one finishes near: no chain offer


def test_no_offer_goes_out_at_night():
    o = offers_with([driver("local", "asema")], ("g1", gig()))
    for minute in (DAY + 23 * HOUR, DAY + 2 * HOUR, DAY + 6 * HOUR + 59):
        assert o.offers("g1", minute, rescue=True) == []
    assert o.offers("g1", DAY + 7 * HOUR, rescue=True) != []


def test_at_most_three_offers_are_open_for_one_gig():
    o = offers_with([driver(f"d{i}", "asema") for i in range(6)], ("g1", gig()))
    first = o.offers("g1", TUESDAY_10, rescue=True)
    assert len(first) == PER_GIG_OPEN
    assert o.offers("g1", TUESDAY_10 + 5, rescue=True) == []  # all three still open
    o.observe({"kind": "offer_answered", "at": TUESDAY_10 + 6, "gigId": "g1", "driverId": "d0", "answer": "declined"})
    assert len(o.offers("g1", TUESDAY_10 + 7, rescue=True)) == 1  # one place freed
    assert len(o.offers("g1", TUESDAY_10 + 11, rescue=True)) == 2  # the other two answer after 10 minutes


def test_no_driver_gets_more_than_three_offers_a_day():
    gigs = [(f"g{i}", gig(until=3 * DAY)) for i in range(5)]
    o = offers_with([driver("local", "asema")], *gigs)
    sent = [a for i in range(5) for a in o.offers(f"g{i}", TUESDAY_10 + i * 15, rescue=True)]
    assert len(sent) == PER_DRIVER_PER_DAY
    assert o.offers("g4", TUESDAY_10 + 23 * HOUR, rescue=True) == []  # still inside 24 hours of the first
    assert o.offers("g4", TUESDAY_10 + DAY + 1, rescue=True) != []


def test_a_manual_car_goes_only_to_drivers_with_a_manual_licence():
    o = offers_with(
        [driver("auto", "asema", licence="automatic_only"), driver("manual", "asema")], ("g1", gig(manual=True))
    )
    assert [a["driverId"] for a in o.offers("g1", TUESDAY_10, rescue=True)] == ["manual"]


def test_a_premium_car_goes_only_to_experienced_drivers():
    roster = [driver("new", "asema", gigs=10), driver("low", "asema", rating=4.5), driver("pro", "asema")]
    o = offers_with(roster, ("g1", gig(experienced=True)))
    assert [a["driverId"] for a in o.offers("g1", TUESDAY_10, rescue=True)] == ["pro"]


def test_a_driver_who_declined_today_is_not_asked_again_today():
    o = offers_with([driver("local", "asema")], ("g1", gig()), ("g2", gig(until=3 * DAY)))
    assert o.offers("g1", TUESDAY_10, rescue=True)
    o.observe(
        {"kind": "offer_answered", "at": TUESDAY_10 + 10, "gigId": "g1", "driverId": "local", "answer": "declined"}
    )
    assert o.offers("g2", TUESDAY_10 + 20, rescue=True) == []
    assert o.offers("g2", 2 * DAY + 10 * HOUR, rescue=True) != []


def test_a_booked_gig_gets_no_offers():
    o = offers_with([driver("local", "asema")], ("g1", gig()))
    o.observe({"kind": "gig_booked", "at": TUESDAY_10, "gigId": "g1", "driverId": "x", "feeCents": 10000})
    assert o.offers("g1", TUESDAY_10, rescue=True) == []


def test_no_offers_below_level_3():
    o = Offers([driver("local", "asema")], world_map(), level=2)
    o.register("g1", gig(), SCHEDULE)
    assert o.offers("g1", TUESDAY_10, rescue=True) == []


def test_a_rescue_asks_drivers_seen_working_today_first():
    o = offers_with([driver("idle", "asema"), driver("busy", "satama")], ("g1", gig()))
    o.observe({"kind": "gig_viewed", "at": TUESDAY_10 - HOUR, "gigId": "g0", "driverId": "busy"})
    assert [a["driverId"] for a in o.offers("g1", TUESDAY_10, rescue=True)] == ["busy", "idle"]


def test_a_gig_past_its_deadline_warning_is_rescued_at_each_step_until_booked():
    o = offers_with([driver(f"d{i}", "asema") for i in range(5)], ("g1", gig()))
    assert o.due(TUESDAY_10) == []  # no one finishes near it, and it is not rescued yet
    o.rescue("g1")
    assert len(o.due(TUESDAY_10)) == PER_GIG_OPEN
    assert len(o.due(TUESDAY_10 + 11)) == 2  # the next drivers, once the first offers have run out
    o.observe({"kind": "gig_booked", "at": TUESDAY_10 + 15, "gigId": "g1", "driverId": "d0", "feeCents": 1})
    assert o.due(TUESDAY_10 + 30) == []
