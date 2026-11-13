"""The bench behind the results in ../README.md: plays practice weeks with a version of dispatch.py
and sums its ledger: driver fees, refunds and penalties, beside the score.

    uv run python strategies/fees/results/bench.py <path to dispatch.py> <level> <seed> [<seed> ...]

Prints one JSON line per seed. In a Claude Code cloud session the kit's client cannot reach the server
with the proxy's team key, because it ignores HTTPS_PROXY: when HTTPS_PROXY is set, this script tunnels
the kit's connections through it, and SPREAD_KEY may be a placeholder that the proxy replaces.
"""

import contextlib
import http.client
import importlib.util
import io
import json
import os
import ssl
import sys
import time
import types
from collections import Counter
from urllib.parse import urlsplit

import spread.client
from spread.client import SpreadError

os.environ.setdefault("SPREAD_URL", "https://spread.bahnexpress.com")
if os.environ.get("HTTPS_PROXY"):
    PROXY = urlsplit(os.environ["HTTPS_PROXY"])
    CONTEXT = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt")

    class Tunnelled(http.client.HTTPSConnection):
        def __init__(self, host, timeout=20, **kw):
            super().__init__(PROXY.hostname, PROXY.port, timeout=60, context=CONTEXT)
            self.set_tunnel(host)

    spread.client.http = types.SimpleNamespace(
        client=types.SimpleNamespace(
            HTTPSConnection=Tunnelled,
            HTTPConnection=http.client.HTTPConnection,
            HTTPException=http.client.HTTPException,
        )
    )
    os.environ.setdefault("SPREAD_KEY", "placeholder-replaced-by-proxy")


def load(path):
    spec = importlib.util.spec_from_file_location(f"dispatch_{abs(hash(path))}", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec.loader.exec_module(module)
    return module


def run(path, level, seed):
    module = load(path)
    refused = Counter()
    original = module.Desk.read_results

    def read_results(self, actions, results):
        for action, result in zip(actions, results):
            if result["ok"] is not True:
                refused[action["type"] + ": " + result["reason"][:60]] += 1
        return original(self, actions, results)

    module.Desk.read_results = read_results
    client = module.Client()
    while True:  # the team's 8 practice slots are shared: wait for one
        try:
            world = client.create(level=level, seed=seed)
            break
        except SpreadError as error:
            if error.status != 409:
                raise
            time.sleep(15)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            module.play_practice(world, level)
    except BaseException:
        world.delete()
        raise
    score = world.score()
    money, delivered, drops = Counter(), 0, 0
    for event in world.events():
        if event["kind"] == "ledger":
            money[event["line"]["kind"]] += event["line"]["cents"]
        delivered += event["kind"] == "delivered"
        drops += event["kind"] == "gig_dropped"
    # What drivers learn: per order, the booked fee over the first fee that a driver viewed.
    views = world.reveal()["views"]
    gig_order = {g["id"]: g["stops"][0]["orderId"] for g in world.snapshot()["gigs"]}
    first_view = {}
    for view in sorted(views, key=lambda v: v["at"]):
        first_view.setdefault(gig_order.get(view["gigId"]), view["feeCents"])
    learned = []
    for event in world.events():
        if event["kind"] == "gig_booked" and gig_order.get(event["gigId"]) in first_view:
            learned.append(event["feeCents"] / first_view.pop(gig_order[event["gigId"]]))
    learned.sort()
    out = {
        "seed": seed,
        "world": world.id,
        "margin": score["marginCents"] / 100,
        "orders": score["wonOrders"],
        "onTime": round(score["onTimeShare"], 4),
        "undelivered": round(score["undeliveredShare"], 4),
        "fees": -money["driver_fee"] / 100,
        "feesPerDelivered": round(-money["driver_fee"] / 100 / max(1, delivered), 2),
        "refunds": -money["late_refund"] / 100,
        "penalties": -money["undelivered_penalty"] / 100,
        "revenue": money["revenue"] / 100,
        "cars": delivered,
        "drops": drops,
        "learnedRaise": round(learned[len(learned) // 2], 3) if learned else None,
        "refused": dict(refused.most_common(5)),
    }
    return out


if __name__ == "__main__":
    path, level, seeds = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    for seed in seeds:
        print(json.dumps(run(path, level, seed)), flush=True)
