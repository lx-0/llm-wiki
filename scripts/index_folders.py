"""Entry module for `wiki index` — the logic lives in `collectors.folder_index`.

Why a separate module: the collector module is imported by name (`collectors.MODULES`) and
configures nothing at import. Run with `python -m`, it would execute as `__main__`, a second
copy beside the one the registry imports, its `@register` included. This entry sets up
logging and exits with `main`'s code. `wiki collect folder-index` is the Registry-shaped
all-roots run; `main(argv)` with the single root and `--force` is this command, and
`wiki collect folder-index -- <flags>` reaches the same function.
"""

from collectors.folder_index import main
from core.console import setup_console_logging

if __name__ == "__main__":
    # Logging is set up here, at the entry point — the collector module configures
    # nothing at import (it is imported by the package and by the Registry run).
    setup_console_logging("folder-index")
    raise SystemExit(main())
