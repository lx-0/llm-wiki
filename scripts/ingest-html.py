"""Runnable entry point for `wiki ingest-html`. Logic lives in preprocessors.html_ingest.

Usage:
    uv run python scripts/ingest-html.py page.html                    # content mode (default)
    uv run python scripts/ingest-html.py page.html --mode visual      # screenshot + vision
    uv run python scripts/ingest-html.py page.html --mode both        # content + visual
    uv run python scripts/ingest-html.py https://example.com          # URL works too
    uv run python scripts/ingest-html.py page.html --no-compile       # don't auto-compile
    uv run python scripts/ingest-html.py page.html --model gemma3:4b  # different model

This file is a thin shim so the `wiki ingest-html` bash command keeps its path.
The `html` Preprocessor (`preprocessors/html_ingest.py`) is the real home; it is
also reachable via `wiki preprocess html <source>`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from preprocessors.html_ingest import main  # noqa: E402

if __name__ == "__main__":
    main()
