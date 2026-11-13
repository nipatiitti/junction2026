"""Our strategies for the dispatch system, one folder per idea, each a subclass of `Strategy`. dispatch.py calls into
them. README.md in this folder lists them."""

from strategies.strategy import NoParams, Strategy

__all__ = ["NoParams", "Strategy"]
