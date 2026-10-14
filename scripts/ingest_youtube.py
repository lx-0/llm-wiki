"""Entry module for `wiki ingest-youtube` — the logic lives in `collectors.scan_youtube`.

Why a separate module: `collectors/__init__.py` imports `scan_youtube` to register the
collector, so running the package module itself with `python -m collectors.scan_youtube`
executes it twice (once on package import, once as `__main__` — Python's runpy warns about
exactly that, and the collector registers twice). A top-level entry module outside the
package has one execution and no warning. `wiki collect youtube` is the Registry-shaped
run; this entry keeps the direct CLI's `--url / --inbox / --tier` flags.
"""

import logging

from collectors.scan_youtube import main

if __name__ == "__main__":
    # Logging stays local to the entry point (see scan_youtube's own __main__ block:
    # a module-level basicConfig would hijack the root logger of every importer).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    raise SystemExit(main())
