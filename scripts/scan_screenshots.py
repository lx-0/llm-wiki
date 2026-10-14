"""Entry script for the screenshots collector's direct CLI — the logic lives in
`collectors.scan_screenshots`.

`wiki collect screenshots` is the Registry-shaped run (what the piggyback spawns). The
flags only the direct CLI offers — `--all`, `--limit N`, `--backfill DAYS`,
`--backfill-thumbnails`, `--retrofit-batch-reports`, `--dry-run` — need an entry outside
the `collectors` package: `collectors/__init__.py` imports `scan_screenshots` to register
it, so `python -m collectors.scan_screenshots` would execute the module twice (runpy warns,
the collector registers twice), and by path the module cannot find `core.*`. A top-level
script has one execution and is run by path from the vault root:

    uv run --project .wiki python .wiki/scripts/scan_screenshots.py --backfill 7
"""

from collectors.scan_screenshots import main
from core.console import setup_console_logging

if __name__ == "__main__":
    # Logging is set up here, at the entry point — the collector module configures
    # nothing at import (it is imported by the package and by the Registry run).
    setup_console_logging("scan-screenshots")
    main()
