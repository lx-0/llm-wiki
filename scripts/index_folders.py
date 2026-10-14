"""Entry module for `wiki index` — the logic lives in `collectors.folder_index`.

Why a separate module: `collectors/__init__.py` imports `folder_index` to register the
`folder-index` collector, so running the package module itself with
`python -m collectors.folder_index` executes it twice (once on package import, once as
`__main__` — Python's runpy warns about exactly that). A top-level entry module outside the
package has one execution and no warning. `wiki collect folder-index` is the Registry-shaped
all-roots run; this entry keeps the CLI's single-root + `--force` flags.
"""

import logging

from collectors.folder_index import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
