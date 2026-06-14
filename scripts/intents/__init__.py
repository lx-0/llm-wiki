"""Intent-dispatch subpackage — classify intake notes into actionable intents.

The `intents` producer (`producers/intents.py`) builds an `Intent` and calls
`dispatch()`, which routes by `Intent.kind` to a registered handler. Handlers
are imported here so their `@register` fires at package import. Adding a new
outcome kind = add a handler module + import it here.
"""

from __future__ import annotations

import logging

from .base import HandlerResult, Intent, IntentHandler, get_handler, register

# Import order doesn't matter (keyed by KIND, not registration order). Each
# import triggers @register at module load.
from . import task_handler as _task_handler  # noqa: E402, F401
from . import idea_handler as _idea_handler  # noqa: E402, F401
from . import note_handler as _note_handler  # noqa: E402, F401

log = logging.getLogger("compile")

__all__ = [
    "Intent",
    "IntentHandler",
    "HandlerResult",
    "get_handler",
    "register",
    "dispatch",
]


def dispatch(intent: Intent) -> HandlerResult:
    """Route `intent` to the handler registered for its kind.

    Unknown / unhandled kind (`none`, or a future kind with no handler yet) is
    a logged no-op, never an error — the producer stays forward-compatible with
    classifier kinds that ship before their handler.
    """
    handler = get_handler(intent.kind)
    if handler is None:
        log.info("  Intent: no handler for kind=%r (no-op)", intent.kind)
        return HandlerResult(kind=intent.kind, status="skipped", reason="no handler")
    return handler.handle(intent)
