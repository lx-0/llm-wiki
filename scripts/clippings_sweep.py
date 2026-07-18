"""Compatibility shim — clippings-sweep logic lives in preprocessors.clippings.

`compile.py` imports this module (`import clippings_sweep; clippings_sweep.sweep()`)
as its pre-compile lift step. Keeping the module name stable here means that
call site (and the `clippings` Preprocessor, reachable via `wiki preprocess
clippings`) share one implementation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from preprocessors.clippings import main, sweep  # noqa: E402,F401

if __name__ == "__main__":
    main()
