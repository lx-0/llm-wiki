"""Entry script for the tab-groups collector's direct CLI — the logic lives in
`collectors.scan_tabs`.

`wiki collect tabs` is the Registry-shaped run. The direct CLI's `--backup-dir` and
`--dry-run` need an entry outside the `collectors` package: `collectors/__init__.py` imports
`scan_tabs` to register it, so `python -m collectors.scan_tabs` would execute the module
twice (runpy warns, the collector registers twice), and by path the module cannot find
`core.*`. Run this script by path from the vault root:

    uv run --project .wiki python .wiki/scripts/scan_tabs.py --dry-run
"""

from collectors.scan_tabs import main

if __name__ == "__main__":
    main()
