"""Admission control: which price requests to take. See README.md."""

from strategies.admission.admission import Admission, Held, Params, Verdict

__all__ = ["Admission", "Held", "Params", "Verdict"]
