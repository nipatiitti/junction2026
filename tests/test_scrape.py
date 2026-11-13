"""Fast tests without network: the explore policy's prices, and when the scraper's client uses the proxy."""

import random

from dispatch import Desk
from scrape import ExploreDesk, ProxyClient, bypasses_proxy

REQUEST = {
    "id": "R1",
    "options": [
        {"kind": "same_day", "deadline": 1200, "listPriceCents": 10000},
        {"kind": "next_day", "deadline": 2640, "listPriceCents": 8000},
    ],
    "referenceFeeCents": 5000,
    "legs": [{}],
}
ORDER = {"id": "R1", "legs": [{}]}


def explore_desk(seed: str = "s-1:8") -> ExploreDesk:
    return ExploreDesk(None, 8, 600, random.Random(seed), (0.7, 1.8), (0.6, 1.6))


def test_explore_quotes_every_option_inside_the_range_and_the_same_for_a_seed():
    first, second = explore_desk(), explore_desk()
    first.quote(REQUEST)
    second.quote(REQUEST)
    quote = first.outbox[0]
    assert quote == second.outbox[0]
    assert set(quote["prices"]) == {"same_day", "next_day"}
    assert 7000 <= quote["prices"]["same_day"] <= 18000
    assert 5600 <= quote["prices"]["next_day"] <= 14400
    other = explore_desk("s-2:8")
    other.quote(REQUEST)
    assert other.outbox[0] != quote


def test_explore_scales_the_starter_fees_by_one_multiple_an_order():
    desk = explore_desk()
    desk.requests["R1"] = REQUEST
    starter = Desk(None, 8, 600)
    starter.requests["R1"] = REQUEST
    base = starter.fees_for(ORDER, 1)
    fees = desk.fees_for(ORDER, 1)
    factor = fees[0]["feeCents"] / base[0]["feeCents"]
    assert 0.6 <= factor <= 1.6
    assert [s["at"] for s in fees] == [s["at"] for s in base]
    assert desk.fees_for(ORDER, 1) == fees  # a repost keeps the order's multiple


def test_no_proxy_entries_match_the_host_and_its_domain():
    assert bypasses_proxy("localhost", "localhost,127.0.0.1")
    assert bypasses_proxy("api.example.com", ".example.com")
    assert bypasses_proxy("api.example.com", "*.example.com")
    assert not bypasses_proxy("spread.bahnexpress.com", "localhost,.svc.cluster.local")


def test_client_tunnels_through_https_proxy_unless_no_proxy_names_the_host(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("NO_PROXY", "localhost")
    assert ProxyClient(url="https://spread.example", key="k").proxy.port == 3128
    assert ProxyClient(url="https://localhost", key="k").proxy is None
    assert ProxyClient(url="http://spread.example", key="k").proxy is None  # only https goes through it
    monkeypatch.delenv("HTTPS_PROXY")
    monkeypatch.delenv("https_proxy", raising=False)
    assert ProxyClient(url="https://spread.example", key="k").proxy is None
