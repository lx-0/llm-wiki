"""Labeled exception suppression — the intentional-swallow seam.

Every *deliberate* except-and-continue in the engine goes through
``swallow(label)`` so suppression is greppable (``grep -rn 'swallow('``)
and every suppressed failure leaves a log line instead of vanishing.
Bare ``except Exception: pass`` is banned — an unattended pipeline's
dominant failure mode is the silent skip, and a swallow that never logs
is indistinguishable from a bug.

Levels (WARNING+ lands in the errors-only log archives, see
``core.console.setup_console_logging``):

- ``"warning"`` (default) — the failure degrades a capability the
  operator would want to know about (history append broken, sub-scan
  failed). Recovered anomalies surface at WARNING per repo convention.
- ``"debug"`` — best-effort cleanup (``agen.aclose()``, IMAP logout)
  and per-item hot-loop fallbacks (one bad date/header among thousands)
  where a WARNING per item would flood the log with noise.

Not for boundaries with a richer contract: adapter seams raise typed
errors (``MailboxReadError`` …), SDK calls route through
``core.sdk_helpers`` (``classify_failure`` + ``log_sdk_failure``), and
collector/producer boundaries log + return typed results. Decision tree
in AGENTS.md § Exception handling.
"""

from __future__ import annotations

import logging
from contextlib import ContextDecorator

log = logging.getLogger(__name__)

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class swallow(ContextDecorator):
    """Suppress ``Exception`` inside the block, logging it with a label.

    Context manager and decorator (via :class:`ContextDecorator`):

        with swallow("dream-entity history append"):
            append_history(...)

        @swallow("usage-ledger exit flush")
        def _flush_on_exit() -> None: ...

    ``BaseException`` subclasses that are not ``Exception``
    (``KeyboardInterrupt``, ``SystemExit``) always propagate, unlogged.
    ``logger`` defaults to this module's logger — pass the call site's
    module logger when its name carries routing/formatting meaning.
    """

    def __init__(
        self,
        label: str,
        *,
        level: str = "warning",
        logger: logging.Logger | None = None,
    ) -> None:
        if level not in _LEVELS:
            raise ValueError(f"swallow level must be one of {sorted(_LEVELS)}, got {level!r}")
        self.label = label
        self.level = _LEVELS[level]
        self.log = logger if logger is not None else log

    def __enter__(self) -> swallow:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            return False
        if not issubclass(exc_type, Exception):
            return False
        self.log.log(self.level, "swallowed [%s]: %s: %s", self.label, exc_type.__name__, exc)
        return True
