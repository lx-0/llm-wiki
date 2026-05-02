"""Mailbox adapters + the kind→adapter dispatcher.

`resolve_reader(account)` and `resolve_filter(account)` map an
`accounts.<id>` config block to a concrete Reader / Filter instance.
Unknown `kind` returns `None` (graceful agnostic — collector skips,
nothing crashes).

Concrete adapters land in S02 (Thunderbird, AllInkl) and S03 (Gmail).
S01 ships only the base Protocols + stub resolvers.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import ApplyResult, MailboxFilter, MailboxReader

log = logging.getLogger(__name__)


def resolve_reader(account: dict[str, Any]) -> MailboxReader | None:
    """Map account.reader.kind to a concrete Reader.

    Returns None if no `reader` block is configured or the kind is unknown.
    Logs a one-line warning on unknown kinds so typos surface.
    """
    reader_cfg = account.get("reader") or {}
    kind = reader_cfg.get("kind")
    if not kind:
        return None

    # Concrete dispatch lands in S02 (thunderbird-mbox) and S03 (gmail-api).
    # S01 stub: everything returns None so EmailCollector exercises the
    # graceful-skip path until the adapters land.
    log.warning(
        "resolve_reader: kind=%r — no adapter registered yet (S01 stub). "
        "Account will be skipped.",
        kind,
    )
    return None


def resolve_filter(account: dict[str, Any]) -> MailboxFilter | None:
    """Map account.filter.kind to a concrete Filter.

    Same shape as resolve_reader; same graceful-skip + warning on
    unknown kinds.
    """
    filter_cfg = account.get("filter") or {}
    kind = filter_cfg.get("kind")
    if not kind:
        return None

    log.warning(
        "resolve_filter: kind=%r — no adapter registered yet (S01 stub). "
        "Account will be skipped.",
        kind,
    )
    return None


__all__ = [
    "ApplyResult",
    "MailboxFilter",
    "MailboxReader",
    "resolve_filter",
    "resolve_reader",
]
