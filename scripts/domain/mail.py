"""Mailbox domain types — frozen dataclasses shared by Readers, Filters, and Collectors.

These describe the *substrate*, not any specific backend. Thunderbird mbox,
Gmail API, IMAP, All-Inkl Procmail all produce / consume these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


# ── Read-side ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MessageMeta:
    """Headers-only view of one message. What a metadata scan returns."""

    id: str                          # backend-specific (mbox key | gmail msgid | imap UID)
    account_id: str                  # which CONFIG.personal.accounts.<id> this came from
    folder: str                      # adapter normalises separator to "/"
    from_addr: str
    to_addrs: tuple[str, ...]
    subject: str
    date: datetime
    size_bytes: int
    in_reply_to: str | None = None   # for thread reconstruction
    message_id: str | None = None    # RFC822 Message-ID


@dataclass(frozen=True)
class Message:
    """Full message — metadata + body + attachment filenames.

    The engine never stores attachment bytes; only filenames are kept so
    the compiler can reference them in articles ("attachment: foo.pdf").
    """

    meta: MessageMeta
    body_text: str
    body_html: str | None = None
    attachment_filenames: tuple[str, ...] = ()


# ── Write-side ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FilterCondition:
    """OR-combined matchers. A message matches if ANY listed pattern fits.

    Empty tuples mean "no constraint on this dimension"; a condition with
    every field empty matches every message (use deliberately).
    """

    from_addrs: tuple[str, ...] = ()
    subject_contains: tuple[str, ...] = ()
    body_contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilterAction:
    """What to do with messages that match the condition."""

    kind: Literal["move", "tag", "flag", "delete"]
    target: str  # folder name (move) | tag name (tag) | "" (flag/delete)


@dataclass(frozen=True)
class FilterRule:
    """A complete rule. Compiler emits these as YAML in raw/suggestions/;
    execute-suggestions resolves the account's MailboxFilter and dispatches.
    """

    name: str
    condition: FilterCondition
    action: FilterAction
