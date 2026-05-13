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
from collectors import email_collector  # noqa: F401,E402
from collectors import jamie  # noqa: F401,E402

__all__ = [
    "Collector",
    "CollectorSpec",
    "RunResult",
    "all_collectors",
    "get_collector",
    "piggyback_collectors",
    "register",
]
