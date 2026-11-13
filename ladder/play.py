"""Plays a Spread week with the ride ladder. From the repository root:

    uv run ladder/play.py --level 8 --seed spread-1      # a practice week
    uv run ladder/play.py --final                        # our copy of a test final or of the final

README.md in this folder has the design and the options. The bench runs this file from its own folder
(`python ladder/play.py --level 8 --seed spread-1`), so it puts the repository root on the import path first:
record.py, spread_proxy.py and the package `ladder` live there.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The root first, and not this folder: a module here must never shadow one of the root's or the standard library's.
sys.path[:] = [str(HERE.parent)] + [p for p in sys.path if Path(p or ".").resolve() != HERE]

from ladder.main import main  # after the path above

if __name__ == "__main__":
    main()
