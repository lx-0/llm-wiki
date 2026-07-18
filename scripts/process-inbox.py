"""Runnable entry point for `wiki process-inbox`. Logic lives in preprocessors.inbox.

Usage:
    uv run python scripts/process-inbox.py                    # process all, then compile
    uv run python scripts/process-inbox.py --no-compile       # process only, don't compile
    uv run python scripts/process-inbox.py --dry-run          # show what would happen
    uv run python scripts/process-inbox.py --model gemma3:4b  # use a different model

This file is a thin shim so the `wiki process-inbox` bash command keeps its
path. The `inbox` Preprocessor (`preprocessors/inbox.py`) is the real home; it
is also reachable via `wiki preprocess inbox`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from preprocessors.inbox import main  # noqa: E402

if __name__ == "__main__":
    main()
