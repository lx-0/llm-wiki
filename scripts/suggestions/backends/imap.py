"""IMAP retroactive actions — move/tag/set-flags on existing messages.

Distinct from MailboxFilter (which creates server-side rules for FUTURE
messages). These functions act on EXISTING messages already in a folder.

Called from `suggestions/cli.py` for `imap-move`, `imap-tag`,
`imap-set-flags` action types. Account credentials are read from
`CONFIG.personal.accounts.<id>` — Gmail accounts use OAuth2, others
use password env-vars (`reader.imap_user_env`/`reader.imap_pass_env`
or filter-side equivalents).

Ported from the legacy `scripts/thunderbird-rules.py` (S02) without
behavior changes.
"""

from __future__ import annotations

import logging
import os
import re

from core.wiki_config import CONFIG

log = logging.getLogger(__name__)


def _account_imap_config(account_id: str) -> tuple[str, str, str, str, str] | None:
    """Returns (host, user_env, pass_env, email, kind) or None."""
    acct = (CONFIG.personal.accounts or {}).get(account_id)
    if not acct:
        return None
    # Pull IMAP creds from filter or reader block, whichever has them.
    for side in ("filter", "reader"):
        side_cfg = acct.get(side) or {}
        host = side_cfg.get("imap_host", "")
        if host:
            return (
                host,
                side_cfg.get("imap_user_env", ""),
                side_cfg.get("imap_pass_env", ""),
                acct.get("email", ""),
                side_cfg.get("kind", ""),
            )
    return None


def _imap_client(account_id: str):
    from imapclient import IMAPClient

    cfg = _account_imap_config(account_id)
    if cfg is None:
        return None, f"No IMAP config for account {account_id!r}"
    host, user_env, pass_env, email_addr, kind = cfg
    if not host:
        return None, f"No imap_host configured for {account_id}"

    client = IMAPClient(host, ssl=True)

    if "gmail" in host or kind == "gmail-api":
        # OAuth2 — token cache lives where GmailFilter put it (.claude/gmail-token-<id>.pickle)
        from adapters.mailbox.gmail import _credentials  # type: ignore[import-not-found]
        creds, err = _credentials(account_id)
        if err:
            return None, err
        client.oauth2_login(email_addr, creds.token)
    else:
        user = os.environ.get(user_env, "")
        passwd = os.environ.get(pass_env, "")
        if not user or not passwd:
            return None, f"IMAP creds not set: {user_env}, {pass_env} (in .claude/.env)"
        client.login(user, passwd)
    return client, None


def _ensure_folder(client, target: str) -> None:
    if not target:
        return
    folders = [name for _flags, _delim, name in client.list_folders()]
    if target not in folders:
        try:
            client.create_folder(target)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not create folder %r: %s", target, e)


def imap_move(
    account_id: str,
    folder: str,
    search: list,
    target: str,
    dry_run: bool = True,
) -> dict:
    """Move messages matching `search` from `folder` to `target`."""
    client, err = _imap_client(account_id)
    if err:
        return {"error": err}
    try:
        client.select_folder(folder)
        uids = client.search(search or ["ALL"])
        stats = {"matched": len(uids), "dry_run": dry_run, "moved": 0}
        if dry_run or not uids:
            return stats
        _ensure_folder(client, target)
        client.move(uids, target)
        stats["moved"] = len(uids)
        return stats
    finally:
        client.logout()


def imap_tag(
    account_id: str,
    folder: str,
    search: list,
    tag: str,
    dry_run: bool = True,
) -> dict:
    client, err = _imap_client(account_id)
    if err:
        return {"error": err}
    try:
        client.select_folder(folder)
        uids = client.search(search or ["ALL"])
        stats = {"matched": len(uids), "dry_run": dry_run, "tagged": 0}
        if dry_run or not uids:
            return stats
        client.add_flags(uids, [tag.encode() if isinstance(tag, str) else tag])
        stats["tagged"] = len(uids)
        return stats
    finally:
        client.logout()


def imap_set_flags(
    account_id: str,
    folder: str,
    search: list,
    flags: list,
    dry_run: bool = True,
) -> dict:
    client, err = _imap_client(account_id)
    if err:
        return {"error": err}
    try:
        client.select_folder(folder)
        uids = client.search(search or ["ALL"])
        stats = {"matched": len(uids), "dry_run": dry_run, "set": 0}
        if dry_run or not uids:
            return stats
        client.add_flags(uids, flags)
        stats["set"] = len(uids)
        return stats
    finally:
        client.logout()


def condition_to_imap_search(condition: str) -> list:
    """Convert a TB-style 'OR (from,is,a) (subject,contains,b)' string to IMAP SEARCH."""
    clauses = re.findall(r"\(([^)]+)\)", condition)
    if not clauses:
        return ["ALL"]
    is_or = condition.strip().startswith("OR")
    criteria: list[list[str]] = []
    for clause in clauses:
        parts = clause.split(",", 2)
        if len(parts) < 3:
            continue
        field_, op, val = parts[0].strip().lower(), parts[1].strip(), parts[2].strip()
        if field_ == "from" and op == "is":
            criteria.append(["FROM", val])
        elif field_ == "subject" and op == "contains":
            criteria.append(["SUBJECT", val])
        elif field_ == "body" and op == "contains":
            criteria.append(["BODY", val])
    if not criteria:
        return ["ALL"]
    if is_or and len(criteria) > 1:
        # IMAP OR is binary; fold left.
        out = criteria[0]
        for c in criteria[1:]:
            out = ["OR"] + out + c
        return out
    # AND-combined (default)
    out: list = []
    for c in criteria:
        out += c
    return out
