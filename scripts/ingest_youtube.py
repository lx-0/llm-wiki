"""Entry module for `wiki ingest-youtube` — the logic lives in `collectors.scan_youtube`.

Why a separate module: the collector module is imported by name (`collectors.MODULES`) and
configures nothing at import. Run with `python -m`, it would execute as `__main__`, a second
copy beside the one the registry imports, its `@register` included. This entry sets up
logging and exits with `main`'s code. `wiki collect youtube` is the Registry-shaped run (the
inbox drain); `main(argv)` with `--url / --inbox / --tier` is this command, and
`wiki collect youtube -- <flags>` reaches the same function.
"""

from collectors.scan_youtube import main
from core.console import setup_console_logging

if __name__ == "__main__":
    # Logging is set up here, at the entry point — the collector module configures
    # nothing at import (it is imported by the package and by the Registry run).
    setup_console_logging("scan-youtube")
    raise SystemExit(main())
