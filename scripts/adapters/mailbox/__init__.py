"""Mailbox adapters + the kind→adapter dispatcher.

`resolve_reader(account)` and `resolve_filter(account)` map an
`accounts.<id>` config block to a concrete Reader / Filter instance.
Unknown `kind` returns `None` (graceful agnostic — collector skips,
nothing crashes).

Currently registered:

| kind                 | Reader                  | Filter                  |
|----------------------|-------------------------|-------------------------|
| thunderbird-mbox     | ThunderbirdMboxReader   | (use other filter kind) |
| thunderbird-msgfilter| —                       | ThunderbirdMsgFilter    |
| all-inkl-procmail    | —                       | AllInklProcmailFilter   |
| gmail-api            | GmailReader             | GmailFilter             |
| imap                 | ImapReader              | —                       |

Read-side (`reader.kind`) and write-side (`filter.kind`) dispatch are
INDEPENDENT — an account can read via Thunderbird mbox and write filter
rules via All-Inkl Procmail (the legacy hybrid).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import ApplyResult, MailboxFilter, MailboxReader, MailboxReadError

log = logging.getLogger(__name__)


def resolve_reader(account: dict[str, Any]) -> MailboxReader | None:
    """Map account.reader.kind to a concrete Reader."""
    reader_cfg = account.get("reader") or {}
    kind = reader_cfg.get("kind")
    if not kind:
        return None

    account_id = account.get("_id", account.get("email", "unknown"))

    if kind == "thunderbird-mbox":
        from .thunderbird import ThunderbirdMboxReader
        from core.wiki_config import CONFIG

        profile_root = Path(CONFIG.personal.thunderbird_profile or "").expanduser()
        mbox_paths = [profile_root / p for p in reader_cfg.get("mbox_paths", [])]
        return ThunderbirdMboxReader(account_id, mbox_paths)

    if kind == "gmail-api":
        from .gmail import GmailReader

        return GmailReader(account_id=account_id)

    if kind == "imap":
        from .imap import ImapReader

        # Env-var *names* only — ImapReader reads os.environ at connect time,
        # same discipline as AllInklProcmailFilter. default_user falls back
        # to account.email when imap_user_env is unset (Gmail: user == email).
        return ImapReader(
            account_id,
            host=reader_cfg.get("imap_host", ""),
            pass_env=reader_cfg.get("imap_pass_env", ""),
            user_env=reader_cfg.get("imap_user_env", ""),
            default_user=account.get("email", ""),
            folders=reader_cfg.get("folders") or None,
        )

    log.warning(
        "resolve_reader: unknown kind=%r for account=%r — account will be skipped",
        kind,
        account_id,
    )
    return None


def resolve_filter(account: dict[str, Any]) -> MailboxFilter | None:
    """Map account.filter.kind to a concrete Filter."""
    filter_cfg = account.get("filter") or {}
    kind = filter_cfg.get("kind")
    if not kind:
        return None

    account_id = account.get("_id", account.get("email", "unknown"))

    if kind == "thunderbird-msgfilter":
        from .thunderbird import ThunderbirdMsgFilter
        from core.wiki_config import CONFIG

        profile_root = Path(CONFIG.personal.thunderbird_profile or "").expanduser()
        filter_paths = [profile_root / p for p in filter_cfg.get("filter_paths", [])]
        return ThunderbirdMsgFilter(account_id, filter_paths)

    if kind == "all-inkl-procmail":
        from .allinkl import AllInklProcmailFilter

        return AllInklProcmailFilter(
            account_id=account_id,
            email_addr=account.get("email", ""),
            imap_pass_env=filter_cfg.get("imap_pass_env", ""),
        )

    if kind == "gmail-api":
        from .gmail import GmailFilter

        return GmailFilter(account_id=account_id)

    log.warning(
        "resolve_filter: unknown kind=%r for account=%r — account will be skipped",
        kind,
        account_id,
    )
    return None


__all__ = [
    "ApplyResult",
    "MailboxFilter",
    "MailboxReadError",
    "MailboxReader",
    "resolve_filter",
    "resolve_reader",
]
