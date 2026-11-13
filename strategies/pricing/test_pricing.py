"""Fast tests without network for the adaptive quoting model."""

from strategies.pricing import Params, PricingModel
from strategies.pricing.model import DAY, HOUR, TRUST_CAP

TUESDAY_10 = DAY + 10 * HOUR
PLACES = {
    "helsinki": (60.1699, 24.9384),
    "espoo": (60.2055, 24.6559),
    "vantaa": (60.2934, 25.0378),
    "tampere": (61.4978, 23.761),
    "oulu": (65.0121, 25.4651),
    "turku": (60.4518, 22.2666),
    "kuopio": (62.8924, 27.677),
    "pori": (61.4851, 21.7975),
}
LANES = [
    ("tampere", "oulu"),
    ("oulu", "turku"),
    ("turku", "kuopio"),
    ("kuopio", "pori"),
    ("pori", "tampere"),
    ("helsinki", "tampere"),
    ("espoo", "oulu"),
]


def request(rid: str, at: int = TUESDAY_10, pickup="tampere", delivery="oulu", dealer="D1", list_price=10_000) -> dict:
    return {
        "id": rid,
        "dealerId": dealer,
        "arrivedAt": at,
        "legs": [{"pickup": {"placeId": pickup}, "delivery": {"placeId": delivery}}],
        "options": [
            {"kind": "next_day", "listPriceCents": list_price},
            {"kind": "within_3_days", "listPriceCents": list_price},
        ],
    }


def won(rid: str, at: int = TUESDAY_10, dealer="D1") -> dict:
    return {"kind": "order_won", "at": at, "order": {"id": rid, "dealerId": dealer}}


def lost(rid: str, at: int = TUESDAY_10) -> dict:
    return {"kind": "order_lost", "at": at, "requestId": rid}


def ledger(kind: str, order_id: str, at: int) -> dict:
    return {"kind": "ledger", "at": at, "line": {"at": at, "kind": kind, "cents": 0, "orderId": order_id}}


def play(model: PricingModel, results: list[bool], at: int = TUESDAY_10, lanes=LANES, prefix="R") -> None:
    """Quotes one request per result on rotating lanes, then feeds its outcome."""
    for i, result in enumerate(results):
        pickup, delivery = lanes[i % len(lanes)]
        rid = f"{prefix}{i}"
        model.price(request(rid, at + i, pickup, delivery), at + i)
        model.observe(won(rid, at + i) if result else lost(rid, at + i))


def test_levels_1_to_3_quote_the_list_price_of_the_first_option():
    for level in (1, 2, 3):
        model = PricingModel(level)
        assert model.price(request("R1", list_price=12_345), TUESDAY_10) == {"next_day": 12_345}


def test_a_world_starts_near_the_middle_of_its_level():
    assert PricingModel(8).price(request("R1"), TUESDAY_10)["next_day"] == 13_500
    assert PricingModel(7).price(request("R1"), TUESDAY_10)["next_day"] == 12_500
    assert PricingModel(5).price(request("R1"), TUESDAY_10)["next_day"] == 10_000


def test_the_multiplier_rises_after_a_run_of_wins():
    model = PricingModel(7)
    before = model.multiplier(request("X"), TUESDAY_10)
    play(model, [True] * 8)
    assert model.multiplier(request("X"), TUESDAY_10) > before


def test_the_multiplier_falls_after_a_run_of_losses():
    model = PricingModel(7)
    before = model.multiplier(request("X"), TUESDAY_10)
    play(model, [False] * 8)
    assert model.multiplier(request("X"), TUESDAY_10) < before


def test_the_multiplier_holds_at_the_target_win_share():
    model = PricingModel(7, params=Params(target_win=0.5))
    before = model.log_m
    play(model, [True, False] * 20)
    assert abs(model.log_m - before) < 1e-9


def test_a_dealer_we_lose_to_gets_a_lower_price_than_the_others():
    model = PricingModel(7)
    for i in range(6):
        model.price(request(f"A{i}", dealer="cheap"), TUESDAY_10)
        model.observe(lost(f"A{i}"))
        model.price(request(f"B{i}", dealer="dear"), TUESDAY_10)
        model.observe(won(f"B{i}", dealer="dear"))
    cheap = model.multiplier(request("X", dealer="cheap"), TUESDAY_10)
    dear = model.multiplier(request("Y", dealer="dear"), TUESDAY_10)
    assert cheap < dear


def test_a_burst_of_losses_on_many_lanes_is_the_price_war_and_it_ends_the_same_evening():
    model = PricingModel(8)
    play(model, [True, False] * 5, at=10 * HOUR, prefix="warm")  # Monday sets the usual level
    usual = model.log_m
    play(model, [False] * 9, at=TUESDAY_10, prefix="early")
    assert model.war_day is None  # a shorter run of losses can be bad luck or a cheaper day
    play(model, [False] * 3, at=TUESDAY_10 + HOUR)
    assert model.war_day == 1
    during = model.multiplier(request("X"), TUESDAY_10 + 2 * HOUR)
    play(model, [False] * 4, at=TUESDAY_10 + 2 * HOUR, prefix="war")  # the war price keeps following the losses
    assert model.multiplier(request("X"), TUESDAY_10 + 3 * HOUR) < during
    # At 18:00 the competitor's prices are back, and the world's multiplier is back at the day's level.
    after = model.multiplier(request("X"), DAY + 18 * HOUR)
    assert model.log_m == usual
    assert after > during
    assert not model.in_war(2 * DAY + 9 * HOUR)


def test_losses_on_one_lane_only_are_not_a_price_war():
    model = PricingModel(8)
    play(model, [True, False] * 5, at=10 * HOUR, prefix="warm")
    play(model, [False] * 25, lanes=[("tampere", "oulu")])
    assert model.war_day is None


def test_a_war_on_monday_is_followed_but_not_flagged():
    model = PricingModel(8)
    play(model, [False] * 25, at=10 * HOUR)
    assert model.war_day is None
    assert model.log_m < PricingModel(8).log_m


def test_the_war_can_be_declined_instead():
    model = PricingModel(8, params=Params(war_decline=True))
    play(model, [True, False] * 5, at=10 * HOUR, prefix="warm")
    play(model, [False] * 12)
    assert model.war_day == 1
    assert model.price(request("W", list_price=10_000), TUESDAY_10 + HOUR)["next_day"] == 100_000


def test_levels_below_8_have_no_price_war():
    model = PricingModel(7)
    play(model, [True, False] * 5, at=10 * HOUR, prefix="warm")
    play(model, [False] * 25)
    assert model.war_day is None


def test_a_region_that_wins_far_more_than_the_rest_is_the_outage_and_gets_dearer_that_day():
    model = PricingModel(7, PLACES)
    start = model.log_m
    play(model, [True, False] * 6, lanes=LANES[:5], prefix="out")  # elsewhere we win half
    helsinki = [("helsinki", "tampere"), ("vantaa", "oulu"), ("espoo", "turku")]
    play(model, [True] * 12, at=TUESDAY_10 + HOUR, lanes=helsinki, prefix="in")  # around Helsinki, every quote
    assert model.outage is not None and {"helsinki", "espoo", "vantaa"} <= model.outage[1]
    # The region's wins no longer lift the price everywhere else.
    assert abs(model.log_m - start) < 1e-9
    inside = request("X", pickup="helsinki", delivery="oulu")
    outside = request("Y", pickup="oulu", delivery="helsinki")
    now = TUESDAY_10 + 2 * HOUR
    assert model.in_outage(inside, now) and not model.in_outage(outside, now)
    assert abs(model.multiplier(inside, now) / model.multiplier(request("Z", pickup="helsinki"), now) - 1) < 1e-9
    assert abs(model.multiplier(inside, now) / model.multiplier(outside, now) - 1.2) < 0.05
    assert not model.in_outage(inside, DAY + 18 * HOUR)
    assert not model.in_outage(inside, 2 * DAY + 10 * HOUR)  # the next day


def test_a_region_that_wins_like_the_rest_is_no_outage():
    model = PricingModel(7, PLACES)
    play(model, [True, False] * 15, lanes=LANES)
    assert model.outage is None


def test_trust_rises_by_one_per_order_on_time_and_caps_at_25():
    model = PricingModel(8)
    for i in range(30):
        model.observe(won(f"O{i}", dealer="D1"))
        model.observe(ledger("revenue", f"O{i}", 3 * DAY + i))
    model.settle(4 * DAY)
    assert model.trust["D1"] == TRUST_CAP


def test_a_late_order_halves_trust_rounded_down():
    model = PricingModel(8)
    for i in range(7):
        model.observe(won(f"O{i}", dealer="D1"))
        model.observe(ledger("revenue", f"O{i}", 3 * DAY + i))
    model.observe(won("LATE", dealer="D1"))
    model.observe(ledger("revenue", "LATE", 3 * DAY + 100))
    model.observe(ledger("late_refund", "LATE", 3 * DAY + 100))
    assert model.trust["D1"] == 3  # 7 on time, then halved: 3
    model.settle(4 * DAY)
    assert model.trust["D1"] == 3  # the late order never counts as on time


def test_trust_raises_that_dealers_price_at_level_8():
    model = PricingModel(8)
    for i in range(10):
        model.observe(won(f"O{i}", dealer="D1"))
        model.observe(ledger("revenue", f"O{i}", 3 * DAY))
    trusted = model.multiplier(request("X", dealer="D1"), 4 * DAY)
    other = model.multiplier(request("Y", dealer="D2"), 4 * DAY)
    assert abs(trusted / other - 1.10) < 1e-9
