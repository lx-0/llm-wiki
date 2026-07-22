"""Generic IMAP reader — the no-local-client, no-GCP-project mailbox path.

For users who run no local mail client and can't / won't create a Google
Cloud project for the Gmail API. Auth is a plain IMAP login: username +
an **app password** held in an environment variable (`config.yaml` carries
only the env-var *name*, never the secret — same discipline as the
`all-inkl-procmail` filter). This is the standard path for consumer Gmail
(App Passwords still work for `@gmail.com` accounts with 2FA enabled as of
2026) and for any other plain IMAP host.

Stateless per the `MailboxReader` Protocol: each call opens a fresh
connection, does its work, logs out. No connection pooling — a collector
run is one search + one batched fetch per folder, then exit.

Failure contract: a configured account that can't be scanned — missing
`imap_host`, unset credential env vars, connect failure, login failure —
raises `MailboxReadError` from `scan_metadata` / `scan_deep`. The collector
catches it, leaves the account's watermark untouched (next run retries) and
surfaces the error. `list_folders` is informational and stays graceful
(catches → `[]`).
"""

from __future__ import annotations

import email
import email.header
import logging
import os
from datetime import datetime, timezone
from typing import Iterator

from adapters.mailbox.base import MailboxReadError
from core.errors import swallow
from domain.mail import Message, MessageMeta

log = logging.getLogger(__name__)

_IMAP_SSL_PORT = 993
_FETCH_BATCH = 500  # UIDs per FETCH round-trip


class ImapReader:
    """Reads a mailbox over IMAP. Auth via username + app password (env var)."""

    def __init__(
        self,
        account_id: str,
        *,
        host: str,
        pass_env: str,
        user_env: str = "",
        default_user: str = "",
        folders: list[str] | None = None,
    ) -> None:
        self._account_id = account_id
        self._host = host
        self._pass_env = pass_env
        self._user_env = user_env
        self._default_user = default_user
        # None → scan every folder; a list → only these (normalised names).
        self._folders = folders

    # ── credentials + connection ─────────────────────────────────────

    def _credentials(self) -> tuple[str, str]:
        """(user, password). Raises MailboxReadError if host/creds are unset."""
        if not self._host:
            raise MailboxReadError(
                f"ImapReader[{self._account_id}]: no imap_host configured"
            )
        user = (os.environ.get(self._user_env, "") if self._user_env else "") or self._default_user
        password = os.environ.get(self._pass_env, "") if self._pass_env else ""
        if not user or not password:
            raise MailboxReadError(
                f"ImapReader[{self._account_id}]: missing IMAP credentials — set "
                f"${self._pass_env or '<imap_pass_env>'} (app password) and either "
                f"${self._user_env or '<imap_user_env>'} or account.email (user)"
            )
        return user, password

    def _connect(self):
        """Open + login an IMAPClient, or raise MailboxReadError on any failure.

        `normalise_times` is an *instance attribute* (not a constructor
        kwarg) in imapclient 3.x. Setting it to False keeps INTERNALDATE
        tz-aware (UTC) instead of flattened to a naive local datetime —
        downstream code must never deal with naive datetimes (see
        KNOWLEDGE.md, the undated-mail regression).
        """
        user, password = self._credentials()
        try:
            from imapclient import IMAPClient
        except ImportError as e:
            raise MailboxReadError(
                f"ImapReader[{self._account_id}]: imapclient not installed "
                "(uv sync should provide it)"
            ) from e
        try:
            client = IMAPClient(self._host, port=_IMAP_SSL_PORT, ssl=True)
            client.normalise_times = False
            client.login(user, password)
            return client
        except Exception as e:  # noqa: BLE001  any connect/login failure
            raise MailboxReadError(
                f"ImapReader[{self._account_id}]: IMAP connect/login failed: "
                f"{type(e).__name__}: {e}"
            ) from e

    # ── folder discovery ─────────────────────────────────────────────

    def list_folders(self) -> list[str]:
        # Informational, not the ingest path — stays graceful (→ []), unlike
        # scan_metadata / scan_deep which let MailboxReadError propagate.
        try:
            client = self._connect()
        except MailboxReadError as e:
            log.warning("ImapReader[%s]: list_folders skipped: %s", self._account_id, e)
            return []
        try:
            return sorted(
                _normalise_folder(name, delim) for _flags, delim, name in client.list_folders()
            )
        except Exception as e:  # noqa: BLE001
            log.warning("ImapReader[%s]: list_folders failed: %s", self._account_id, e)
            return []
        finally:
            _quiet_logout(client)

    def _target_folders(self, client) -> list[tuple[str, str]]:
        """(raw_name, normalised_name) pairs to scan, honouring the optional allowlist.

        Skips `\\Noselect` / `\\NonExistent` folders — IMAP hierarchy parents
        that exist in the namespace but cannot be SELECTed (Gmail's `[Gmail]`
        container is the canonical case; selecting it raises `[NONEXISTENT]`).
        """
        out: list[tuple[str, str]] = []
        for flags, delim, name in client.list_folders():
            flag_names = {f.decode() if isinstance(f, bytes) else f for f in flags}
            if r"\Noselect" in flag_names or r"\NonExistent" in flag_names:
                continue
            norm = _normalise_folder(name, delim)
            if self._folders is not None and norm not in self._folders:
                continue
            out.append((name, norm))
        return out

    # ── metadata scan ────────────────────────────────────────────────

    def scan_metadata(
        self,
        folder: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[MessageMeta]:
        client = self._connect()  # raises MailboxReadError on connect/login failure
        try:
            targets = self._target_folders(client)
            if folder is not None:
                targets = [(r, n) for r, n in targets if n == folder]
            # IMAP SEARCH SINCE is date-granular — it narrows the server-side
            # fetch cheaply; the precise watermark is re-applied in Python below.
            criteria = ["SINCE", since.date()] if since is not None else ["ALL"]
            for raw_name, norm_name in targets:
                try:
                    client.select_folder(raw_name, readonly=True)
                    uids = client.search(criteria)
                except Exception as e:  # noqa: BLE001
                    log.warning("ImapReader[%s]: scan of %r failed: %s",
                                self._account_id, norm_name, e)
                    continue
                for batch in _chunks(uids, _FETCH_BATCH):
                    fetched = client.fetch(batch, ["ENVELOPE", "RFC822.SIZE", "INTERNALDATE"])
                    for uid, data in fetched.items():
                        date = _message_date(data)
                        # Delta mode: drop messages older than the precise
                        # watermark, and drop undated ones (can't be placed
                        # relative to it) — same rule as ThunderbirdMboxReader.
                        if since is not None and (date is None or date < since):
                            continue
                        yield _meta_from_fetch(uid, data, date, self._account_id, norm_name)
        finally:
            _quiet_logout(client)

    # ── deep scan (bodies) ───────────────────────────────────────────

    def scan_deep(
        self,
        folder: str,
        limit: int = 0,
        since: datetime | None = None,
    ) -> Iterator[Message]:
        client = self._connect()  # raises MailboxReadError on connect/login failure
        try:
            targets = [(r, n) for r, n in self._target_folders(client) if n == folder]
            criteria = ["SINCE", since.date()] if since is not None else ["ALL"]
            emitted = 0
            for raw_name, norm_name in targets:
                try:
                    client.select_folder(raw_name, readonly=True)
                    uids = client.search(criteria)
                except Exception as e:  # noqa: BLE001
                    log.warning("ImapReader[%s]: deep scan of %r failed: %s",
                                self._account_id, norm_name, e)
                    continue
                for batch in _chunks(uids, _FETCH_BATCH):
                    fetched = client.fetch(
                        batch, ["ENVELOPE", "RFC822.SIZE", "INTERNALDATE", "RFC822"]
                    )
                    for uid, data in fetched.items():
                        date = _message_date(data)
                        if since is not None and (date is None or date < since):
                            continue
                        meta = _meta_from_fetch(uid, data, date, self._account_id, norm_name)
                        body_text, attachments = _parse_rfc822(data.get(b"RFC822"))
                        yield Message(
                            meta=meta,
                            body_text=body_text,
                            attachment_filenames=attachments,
                        )
                        emitted += 1
                        if limit and emitted >= limit:
                            return
        finally:
            _quiet_logout(client)


# ── helpers ──────────────────────────────────────────────────────────


def _normalise_folder(name: str, delim: bytes | str | None) -> str:
    """Folder name with the server's hierarchy delimiter rewritten to "/"."""
    d = delim.decode() if isinstance(delim, bytes) else (delim or "/")
    return name.replace(d, "/") if d and d != "/" else name


def _chunks(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _quiet_logout(client) -> None:
    with swallow("imap logout", level="debug", logger=log):  # best-effort cleanup
        client.logout()


def _message_date(data: dict) -> datetime | None:
    """tz-aware UTC date from the ENVELOPE Date header, falling back to
    INTERNALDATE. Returns None if neither is present/parseable — the caller
    treats that as "undated" (skipped in delta mode).
    """
    env = data.get(b"ENVELOPE")
    dt = getattr(env, "date", None) if env is not None else None
    if dt is None:
        dt = data.get(b"INTERNALDATE")
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _decode_mime(raw: bytes | str | None) -> str:
    """Decode an RFC 2047-encoded header (subject) to plain text."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        return str(email.header.make_header(email.header.decode_header(raw)))
    except Exception as e:  # noqa: BLE001 — per-header fallback, raw form is usable
        log.debug("MIME header decode failed [%.60s]: %s", raw, e)
        return raw


def _decode_plain(raw: bytes | str | None) -> str | None:
    """Bytes → str for non-encoded headers (Message-ID, In-Reply-To)."""
    if raw is None:
        return None
    return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)


def _addr_str(addr) -> str:
    """imapclient Address namedtuple → "mailbox@host"."""
    if addr is None:
        return ""
    mailbox = (addr.mailbox or b"").decode("utf-8", "replace")
    host = (addr.host or b"").decode("utf-8", "replace")
    if mailbox and host:
        return f"{mailbox}@{host}"
    return mailbox or host


def _meta_from_fetch(
    uid: int, data: dict, date: datetime | None, account_id: str, folder: str
) -> MessageMeta:
    env = data.get(b"ENVELOPE")
    from_addr = ""
    to_addrs: tuple[str, ...] = ()
    subject = ""
    in_reply_to: str | None = None
    message_id: str | None = None
    if env is not None:
        from_list = env.from_ or ()
        from_addr = _addr_str(from_list[0]) if from_list else ""
        to_addrs = tuple(_addr_str(a) for a in (env.to or ()) if a is not None)
        subject = _decode_mime(env.subject)
        in_reply_to = _decode_plain(env.in_reply_to)
        message_id = _decode_plain(env.message_id)
    return MessageMeta(
        id=str(uid),
        account_id=account_id,
        folder=folder,
        from_addr=from_addr,
        to_addrs=to_addrs,
        subject=subject,
        # Epoch fallback is tz-aware — a naive datetime here would crash
        # min()/max() in the report renderers (see KNOWLEDGE.md).
        date=date or datetime.fromtimestamp(0, timezone.utc),
        size_bytes=int(data.get(b"RFC822.SIZE") or 0),
        in_reply_to=in_reply_to,
        message_id=message_id,
    )


def _parse_rfc822(raw: bytes | None) -> tuple[str, tuple[str, ...]]:
    """Full-message bytes → (plain-text body, attachment filenames)."""
    if not raw:
        return "", ()
    msg = email.message_from_bytes(raw)
    return _extract_body(msg), tuple(_attachment_names(msg))


def _extract_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return (part.get_payload(decode=True) or b"").decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception as e:  # noqa: BLE001 — per-message fallback to empty body
                    log.debug("multipart body decode failed: %s", e)
                    return ""
        return ""
    try:
        return (msg.get_payload(decode=True) or b"").decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception as e:  # noqa: BLE001 — per-message fallback to empty body
        log.debug("body decode failed: %s", e)
        return ""


def _attachment_names(msg) -> Iterator[str]:
    if not msg.is_multipart():
        return
    for part in msg.walk():
        if "attachment" in (part.get("Content-Disposition", "") or "").lower():
            name = part.get_filename()
            if name:
                yield _decode_mime(name)
