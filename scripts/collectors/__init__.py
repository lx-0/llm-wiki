"""Collectors — substrate-shaped raw/ writers.

Importing this package triggers `@register` for every Collector
subclass in submodules listed below. New Collector? Add a submodule
and import it here.
"""

from collectors.base import (  # noqa: F401  re-export the public API
    Collector,
    CollectorSpec,
    RunResult,
    all_collectors,
    get_collector,
    piggyback_collectors,
    register,
)

# Trigger @register side-effects.
# Note: calendar_collector.py is named with a `_collector` suffix to avoid
# shadowing the stdlib `calendar` module — `http.cookiejar` does
# `from calendar import timegm`, and `scripts/collectors/` sits on sys.path
# when `cli.py` runs directly. Same fix pattern as email_collector.py.
from collectors import calendar_collector  # noqa: F401,E402
from collectors import email_collector  # noqa: F401,E402
from collectors import gmeet  # noqa: F401,E402
from collectors import health  # noqa: F401,E402
from collectors import jamie  # noqa: F401,E402
from collectors import scan_browser  # noqa: F401,E402
from collectors import scan_screenshots  # noqa: F401,E402
from collectors import scan_tabs  # noqa: F401,E402
from collectors import scan_youtube  # noqa: F401,E402
from collectors import pictures  # noqa: F401,E402
from collectors import voice  # noqa: F401,E402

__all__ = [
    "Collector",
    "CollectorSpec",
    "RunResult",
    "all_collectors",
    "get_collector",
    "piggyback_collectors",
    "register",
]
