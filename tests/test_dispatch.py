"""Fast tests without network: the client's checks, and the starter's reading of dealer notes."""

import pytest
from spread import Client, SpreadError

from dispatch import DAY, HOUR, window_from_note

# Port 9 is the discard port: a request that slipped past the client's checks would fail as unreachable.
OFFLINE = "http://127.0.0.1:9"
# A stop that is open for the whole of Tuesday.
TUESDAY = {"from": DAY, "to": 2 * DAY}


def test_client_does_not_start_without_a_team_key(monkeypatch):
    monkeypatch.delenv("SPREAD_KEY", raising=False)
    with pytest.raises(SpreadError, match="SPREAD_KEY is not set"):
        Client(url=OFFLINE)


def test_client_refuses_a_number_with_a_fraction_before_it_sends():
    world = Client(url=OFFLINE, key="test-key").world("w-test")
    with pytest.raises(SpreadError, match="12345.5 is not a whole number"):
        world.act([{"type": "quote", "requestId": "R00001", "prices": {"next_day": 12345.5}}])


def test_note_with_a_latest_pickup_time_ends_the_pickup_window_then():
    note = {"text": "Nouto ennen klo 15.30."}
    assert window_from_note(note, TUESDAY, "pickup") == {"from": DAY, "to": DAY + 15 * HOUR + 30}


def test_note_with_a_ready_time_starts_the_pickup_window_then():
    note = {"text": "Klar efter kl. 12"}
    assert window_from_note(note, TUESDAY, "pickup") == {"from": DAY + 12 * HOUR, "to": 2 * DAY}


def test_note_about_the_delivery_leaves_the_pickup_window_alone():
    note = {"text": "Deliver by 19:00"}
    assert window_from_note(note, TUESDAY, "pickup") == TUESDAY
    assert window_from_note(note, TUESDAY, "delivery") == {"from": DAY, "to": DAY + 19 * HOUR}
