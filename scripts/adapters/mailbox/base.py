"""Mailbox adapter Protocols (read + filter) — the seam between Collectors and backends.

Both Protocols are stateless from the *interface's* perspective: a caller
constructs an adapter once per account-per-run, then makes any number of
calls. Adapters MAY cache connections internally; the contract doesn't
require it.

Read and Filter are *independent* seams. An account can use a Thunderbird
mbox Reader and an All-Inkl Procmail Filter simultaneously (the legacy
hybrid) — `resolve_reader(account)` and `resolve_filter(account)` are
unrelated calls that may dispatch to different adapter modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol, runtime_checkable

from domain.mail import FilterRule, Message, MessageMeta


# ── Failure signal ───────────────────────────────────────────────────

class MailboxReadError(RuntimeError):
    """A reader could not complete a scan of a *configured* account.

    Raised for: missing/invalid credentials, connect failure, login failure,
    an aborting backend error. NOT raised for "scanned fine, 0 new messages"
    (that stays an empty iterator) nor for "no reader configured" (such an
    account never reaches the scan loop).

    The collector catches this per-account: it leaves the account's watermark
    untouched (so the next run retries the same window — self-healing) and
    surfaces the error instead of silently advancing past unread mail.
    """


# ── Read side ────────────────────────────────────────────────────────

@runtime_checkable
class MailboxReader(Protocol):
    """Read-side mailbox adapter.

    Implementations live in `adapters/mailbox/<backend>.py`. Tests can
    instantiate fake readers directly without going through a Registry —
    the Protocol is the test surface.
    """

    def list_folders(self) -> list[str]:
        """Return the folder/label namespace this account exposes.

        Folder paths use "/" as separator, normalised across backends
        (Thunderbird mbox uses ".", IMAP uses "/", Gmail uses labels —
        all flatten into a "/" tree on the way out).
        """
        ...

    def scan_metadata(
        self,
        folder: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[MessageMeta]:
        """Yield headers-only metadata for messages.

        - `folder=None` → all folders (one of the few cases where the
          adapter walks the whole namespace).
        - `since=None` → no time filter.

        Returns an iterator so backends can stream large mailboxes
        without loading everything into memory at once.
        """
        ...

    def scan_deep(
        self,
        folder: str,
        limit: int = 0,
        since: datetime | None = None,
    ) -> Iterator[Message]:
        """Yield full Message objects (metadata + body + attachment names).

        - `limit=0` → no cap.
        - Used by curiosity-loop deep scans, not by routine metadata sweeps.
        """
        ...


# ── Write side ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ApplyResult:
    """What `MailboxFilter.apply()` returns — feedback for `suggestions/cli.py`."""

    success: bool
    rule_id: str | None = None  # backend's id for the persisted rule, when known
    message: str = ""           # human-readable; appears in operator-facing logs
    dry_run: bool = False


@runtime_checkable
class MailboxFilter(Protocol):
    """Write-side mailbox adapter — applies sorting rules server-side.

    Backends differ widely:
    - Thunderbird msgFilterRules.dat (local file, applies on TB launch)
    - All-Inkl Webmail Procmail (server-side .procmailrc, applies immediately)
    - Gmail API filters.create (server-side, applies on next message)

    The Filter Protocol abstracts these into apply/list. Whether the
    rule activates immediately or on next-launch is a backend property,
    not part of the contract.
    """

    def apply(self, rule: FilterRule, *, dry_run: bool = False) -> ApplyResult:
        """Persist a rule. Idempotent — implementations dedup against
        list_existing() before creating, so re-running doesn't duplicate.

        `dry_run=True` formats the would-be call but doesn't dispatch
        it. Returns ApplyResult(success=True, dry_run=True, message=…).
        """
        ...

    def list_existing(self) -> list[FilterRule]:
        """Return the rules currently configured for this account.

        Used for dedup-on-create and for operator-facing audits.
        """
        ...
