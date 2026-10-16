"""Collectors — substrate-shaped raw/ writers.

`MODULES` names every collector and the module that defines it. Importing this package
imports none of them: `get_collector(name)` imports that collector's module on first use, and
its `@register` fills the registry; `all_collectors()` imports them all, in this table's order
(M034-S06-T03). New Collector? Add a submodule and a row here —
`tests/test_collector_registry.py` refuses a module that `@register`s without one.
"""

from collectors.base import (
    Collector,
    CollectorSpec,
    RunResult,
    all_collectors,
    get_collector,
    piggyback_collectors,
    register,
)

# SPEC name → module. The order is the order `all_collectors()`, `wiki collect --list` and
# piggyback discovery report them in.
# calendar_collector.py, email_collector.py and capture_collector.py carry a `_collector`
# suffix so no module shadows a stdlib name (`http.cookiejar` does `from calendar import
# timegm`); the SPEC names stay clean.
MODULES: dict[str, str] = {
    "calendar": "collectors.calendar_collector",
    "email": "collectors.email_collector",
    "folder-index": "collectors.folder_index",
    "gmeet": "collectors.gmeet",
    "health": "collectors.health",
    "jamie": "collectors.jamie",
    "wispr": "collectors.wispr",
    "browser": "collectors.scan_browser",
    "screenshots": "collectors.scan_screenshots",
    "tabs": "collectors.scan_tabs",
    "youtube": "collectors.scan_youtube",
    "pictures": "collectors.pictures",
    "voice": "collectors.voice",
    "capture": "collectors.capture_collector",
}

__all__ = [
    "MODULES",
    "Collector",
    "CollectorSpec",
    "RunResult",
    "all_collectors",
    "get_collector",
    "piggyback_collectors",
    "register",
]
