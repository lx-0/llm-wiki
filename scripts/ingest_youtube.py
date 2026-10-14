"""Entry module for `wiki ingest-youtube` — the logic lives in `collectors.scan_youtube`.

Why a separate module: `collectors/__init__.py` imports `scan_youtube` to register the
collector, so running the package module itself with `python -m collectors.scan_youtube`
executes it twice (once on package import, once as `__main__` — Python's runpy warns about
exactly that, and the collector registers twice). A top-level entry module outside the
package has one execution and no warning. `wiki collect youtube` is the Registry-shaped
run; this entry keeps the direct CLI's `--url / --inbox / --tier` flags.
"""

from collectors.scan_youtube import main
from core.console import setup_console_logging

if __name__ == "__main__":
    # Logging is set up here, at the entry point — the collector module configures
    # nothing at import (it is imported by the package and by the Registry run).
    setup_console_logging("scan-youtube")
    raise SystemExit(main())
