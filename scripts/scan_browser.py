"""Entry script for the browser collector's direct CLI — the logic lives in
`collectors.scan_browser`.

`wiki collect browser` is the Registry-shaped run (every available source). The direct
CLI's `--source firefox|chrome|all` and `--dry-run` need an entry outside the `collectors`
package: `collectors/__init__.py` imports `scan_browser` to register it, so
`python -m collectors.scan_browser` would execute the module twice (runpy warns, the
collector registers twice), and by path the module cannot find `core.*`. Run this script by
path from the vault root:

    uv run --project .wiki python .wiki/scripts/scan_browser.py --source firefox
"""

from collectors.scan_browser import main

if __name__ == "__main__":
    main()
