"""The mixed system: the ceiling system (strategies/ceiling) with any number of the changes built on it, at the same
time. See README.md next to this file. Issue #209.

A layer is one folder's change to the ceiling system: the class it puts in the desk's admission, pricing, fees or
bundling, and for some a step of its own in the desk. The mixed desk builds each part from the layers named with
`--layers`. Two layers that change the same part become one class that inherits from both, as
strategies/scarcity_ceiling combines two: each class calls the next one's method, so every change applies. A set of
layers whose classes cannot be one class is refused before a world is created.

Everything else (the loop, posting, notes, retries, direct offers, the final) is the root dispatch.py, and the quote
is the ceiling system's, so their improvements reach a mix too.

Run it from the repository root: uv run strategies/tournament/mix.py --layers slack_fees,tempo --level 8 --seed spread-1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run as a file, Python looks for modules next to it; dispatch.py, tools/ and strategies/ are at the root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, fields
from functools import partial
from importlib import import_module

from spread.client import World

import dispatch as root
from strategies.ceiling import dispatch as ceiling
from tools import record

# The parts of the desk that a layer can replace, each with the class the ceiling system has there.
BASE = {
    "admission": "strategies.ceiling:ChainAdmission",
    "pricing": "strategies.ceiling:CeilingPricing",
    "fees": "strategies.fees:FeePlanner",
    "bundler": "strategies.bundling:Bundler",
}


@dataclass(frozen=True)
class Layer:
    """One folder's change to the ceiling system: the class it puts in each part that it replaces, as
    "module:Class". The modules are loaded only for the layers of a mix."""

    admission: str = ""
    pricing: str = ""
    fees: str = ""
    bundler: str = ""
    desk: bool = False  # its dispatch.py's `Desk` adds a step to handle, carry or quote, which the mixed desk keeps
    system: bool = True  # its folder's dispatch.py is the ceiling system with this layer alone


# The layers, in the order their classes and desks are stacked: the first named is asked first and calls the next.
# option_menu's desk writes the ceiling quote out again instead of calling it, so it comes after war_guard, whose
# desk prepares admission and then calls the next quote.
LAYERS: dict[str, Layer] = {
    "slack_fees": Layer(fees="strategies.slack_fees:SlackFeePlanner"),
    "war_guard": Layer(
        admission="strategies.war_guard:WarGuardAdmission", pricing="strategies.war_guard:WarGuardPricing", desk=True
    ),
    "tempo": Layer(admission="strategies.tempo:TempoAdmission", desk=True),
    "learned_cost": Layer(admission="strategies.learned_cost:LearnedCostAdmission", desk=True),
    "trust_value": Layer(admission="strategies.trust_value:TrustValueAdmission"),
    "scarcity_ceiling": Layer(admission="strategies.scarcity_ceiling:ChainScarcityAdmission"),
    "profit_max": Layer(pricing="strategies.profit_max:ProfitPricing"),
    "option_menu": Layer(desk=True),
    "bundling_more": Layer(bundler="strategies.bundling_more:WaitingBundler", system=False),
    "bundling_cheaper": Layer(bundler="strategies.bundling_cheaper:CheapBundler", system=False),
}

# Layers that run together but add nothing: the mix would play the same week as the mix without one of them.
POINTLESS = {
    frozenset({"scarcity_ceiling", "tempo"}): "scarcity_ceiling drops the capacity gate, which is all that tempo "
    "changes: with both, the week is scarcity_ceiling's"
}


def parse_layers(text: str) -> list[str]:
    """The layers of a comma-separated list, in the order of `LAYERS`, whatever order they were named in."""
    wanted = {name.strip() for name in text.split(",") if name.strip()}
    unknown = sorted(wanted - LAYERS.keys())
    if unknown:
        raise ValueError(f"no such layer: {', '.join(unknown)}. The layers are: {', '.join(LAYERS)}")
    return [name for name in LAYERS if name in wanted]


def label(layers: Sequence[str]) -> str:
    """The name of a line-up, as the tournament prints it: ceiling+slack_fees+tempo."""
    return "+".join(["ceiling", *layers])


def policy(layers: Sequence[str]) -> str:
    """The policy of a mix's saved weeks, so each line-up forms its own group in out/spread.sqlite."""
    return f"mix:{label(layers)}"


def files(layers: Sequence[str]) -> list[Path]:
    """The files a mix loads by name for its layers, which no import statement shows: the tournament reads them to
    know whether a saved week is still that mix's."""
    found = [Path(__file__).resolve()]
    for name in layers:
        layer = LAYERS[name]
        for part in BASE:
            if path := getattr(layer, part):
                found.append(ROOT.joinpath(*path.partition(":")[0].split("."), "__init__.py"))
        if layer.desk:
            found.append(ROOT / "strategies" / name / "dispatch.py")
    return found


# The classes


def load(path: str) -> type:
    """The class that "module:Class" names."""
    module, _, name = path.partition(":")
    return getattr(import_module(module), name)


def params_of(cls: type) -> type | None:
    """A strategy class's thresholds: the frozen dataclass `Params` of its module (strategies/README.md), or None
    for a class that keeps none, as the fees do."""
    return getattr(sys.modules[cls.__module__], "Params", None)


def defaults(params: type | None) -> dict[str, object]:
    """Each threshold of a `Params` class with its default value."""
    if params is None:
        return {}
    tuned = params()
    return {field.name: getattr(tuned, field.name) for field in fields(tuned)}


def own(base: type, cls: type) -> dict[str, object]:
    """The thresholds that a layer's class adds to its part's base, or sets to another value."""
    usual = defaults(params_of(base))
    return {key: value for key, value in defaults(params_of(cls)).items() if key not in usual or usual[key] != value}


def clash(part: str, base: type, named: list[tuple[str, type]]) -> str | None:
    """Why the layers' classes for one part cannot be one class, or None. Two of them give one threshold different
    values, so one `Params` cannot hold both; or two of them define one method that the part's base does not have,
    so one would hide the other's."""
    set_by: dict[str, tuple[str, object]] = {}  # threshold -> the layer that sets it, and its value
    defined_by: dict[str, str] = {}  # method -> the layer that defines it
    for name, cls in named:
        for key, value in own(base, cls).items():
            other, was = set_by.setdefault(key, (name, value))
            if was != value:
                return f'{other} and {name} both set the {part} threshold "{key}", to {was} and to {value}'
        for method in vars(cls):
            if not method.startswith("__") and not hasattr(base, method):
                other = defined_by.setdefault(method, name)
                if other != name:
                    return f"{other} and {name} both define `{method}` for {part}"
    return None


def combine(part: str, layers: Sequence[str]) -> type:
    """The class for one part of the desk. Without a layer for the part it is the ceiling system's, with one it is
    that layer's own, and with several it inherits from them all, in the order of `LAYERS`. Its thresholds are the
    base's with what each layer adds or sets: a plain `Params` that inherits from the layers' would take every
    threshold from the first of them, also those that a later layer sets."""
    base = load(BASE[part])
    named = [(name, load(path)) for name in layers if (path := getattr(LAYERS[name], part))]
    classes = [cls for _, cls in named]
    if len(classes) < 2:
        return classes[0] if classes else base
    if why := clash(part, base, named):
        raise ValueError(why)
    theirs = list(dict.fromkeys(p for cls in classes if (p := params_of(cls)) is not None))
    merged: type | None = None
    if theirs:
        kinds = {field.name: field.type for p in theirs for field in fields(p)}
        values = {key: value for cls in classes for key, value in own(base, cls).items()}
        body = {"__annotations__": {key: kinds[key] for key in values}, "__doc__": "The layers' thresholds.", **values}
        merged = dataclass(frozen=True)(type("Params", tuple(theirs), body))

    def __init__(self, roster, world_map, level: int = 8, params=None) -> None:
        super(mixed, self).__init__(roster, world_map, level, params or (merged() if merged else None))

    doc = f"The {part} of {' and '.join(name for name, _ in named)}, in one strategy."
    mixed = type("Mixed" + base.__name__, tuple(classes), {"__init__": __init__, "__doc__": doc})
    return mixed


def problem(layers: Sequence[str]) -> str | None:
    """Why the layers cannot be one system, or None when they can."""
    for pair, why in POINTLESS.items():
        if pair <= set(layers):
            return why
    for part in BASE:
        try:
            combine(part, layers)
        except (TypeError, ValueError) as error:  # TypeError: Python finds no order to inherit from the classes in
            return str(error)
    return None


# The desk


def desk_class(layers: Sequence[str]) -> type[root.Desk]:
    """The ceiling desk with the layers. It inherits from the `Desk` of each layer that adds a step, so every
    such step runs, and puts the mix's own class in each part once they have built theirs."""
    parts = {part: combine(part, layers) for part in BASE}
    steps = [import_module(f"strategies.{name}.dispatch").Desk for name in layers if LAYERS[name].desk]

    class Desk(*(steps or [ceiling.Desk])):
        """The ceiling desk with the strategies and the desk steps of the layers."""

        def __init__(self, world: World, level: int, now: int):
            super().__init__(world, level, now)
            roster, world_map = self.admission.roster, self.admission.world_map  # loaded once by the root desk
            kept = (self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler)
            more = [s for s in self.strategies if all(s is not known for known in kept)]  # option_menu's menu
            for part, cls in parts.items():
                setattr(self, part, cls(roster, world_map, level))
            if hasattr(self.admission, "trust_of"):  # trust_value: admission reads the trust that pricing counts
                self.admission.trust_of = lambda dealer: self.pricing.trust.get(dealer, 0)
            self.strategies = [self.notes, self.admission, self.pricing, self.fees, self.offers, self.bundler, *more]

    return Desk


def main() -> None:
    """Reads `--layers`, then plays as the root dispatch.py does, with the mixed desk: every other option is its."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--layers", default="")
    args, rest = parser.parse_known_args()
    try:
        layers = parse_layers(args.layers)
    except ValueError as error:
        sys.exit(f"mix: {error}")
    if why := problem(layers):
        sys.exit(f"mix: {why}")
    if {"-h", "--help"} & set(rest):
        print(f"--layers a,b: the changes to play on the ceiling system, of: {', '.join(LAYERS)}\n")
    sys.argv = [sys.argv[0], *rest]
    # The root loop (play_practice, play_final) plays with this desk, and main() saves its weeks as the mix's.
    root.Desk = desk_class(layers)
    root.Recorder = partial(record.Recorder, policy=policy(layers))
    root.main()


if __name__ == "__main__":
    main()
