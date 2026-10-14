"""Collectors — substrate-shaped raw/ writers.

Importing this package triggers `@register` for every Collector
subclass in submodules listed below. New Collector? Add a submodule
and import it here.
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

# Trigger @register side-effects. Import order = registration order = the order
# `all_collectors()` / `wiki collect --list` / piggyback discovery report them in.
# The sorter is switched off for this block — alphabetising it would change
# that order (the action comment must stand alone on its line).
# Note: calendar_collector.py is named with a `_collector` suffix to avoid
# shadowing the stdlib `calendar` module — `http.cookiejar` does
# `from calendar import timegm`, and `scripts/collectors/` sits on sys.path
# when `cli.py` runs directly. Same fix pattern as email_collector.py.
# capture_collector.py uses the `_collector` suffix (same defensive naming as
# calendar_collector / email_collector). The SPEC name stays clean ("capture").
# isort: off
from collectors import calendar_collector
from collectors import email_collector
from collectors import folder_index
from collectors import gmeet
from collectors import health
from collectors import jamie
from collectors import wispr
from collectors import scan_browser
from collectors import scan_screenshots
from collectors import scan_tabs
from collectors import scan_youtube
from collectors import pictures
from collectors import voice
from collectors import capture_collector
# isort: on

__all__ = [
    "Collector",
    "CollectorSpec",
    "RunResult",
    "all_collectors",
    "get_collector",
    "piggyback_collectors",
    "register",
]
