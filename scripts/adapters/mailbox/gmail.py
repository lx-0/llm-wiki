"""Gmail Reader + Filter adapters via Gmail API.

S02 shipped GmailFilter (server-side rule creation).
S03 adds GmailReader (read-side label/message scanning) plus an OAuth
bootstrap UX via `wiki gmail-auth <account-id>` and a JSON token cache
at `<.wiki>/state/gmail-token-<id>.json`.

OAuth client secret resolved by `_resolve_oauth_client()`: prefers
`<vault>/.claude/google-oauth-client.json` (shared with gmeet +
calendar), falls back to `<vault>/.claude/gmail-oauth-client.json`
(per-install, gitignored). Operator places the file once after creating
an OAuth client at https://console.cloud.google.com.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator

from adapters.mailbox.base import ApplyResult, MailboxReadError
from core import google_oauth
from core.paths import ROOT_DIR
from core.google_oauth import OAuthApp
from domain.mail import FilterRule, Message, MessageMeta

log = logging.getLogger(__name__)


# Primary OAuth client = the neutral `google-oauth-client.json` (the same
# project that gmeet + calendar already use; their OAuth flow is verified
# and the operator has Test users + scopes set up there). Fallback to the
# legacy `gmail-oauth-client.json` for installs that haven't consolidated
# yet. Mirrors `collectors.calendar_collector._resolve_oauth_client`.
_OAUTH_CLIENT_PRIMARY = ROOT_DIR / ".claude" / "google-oauth-client.json"
_OAUTH_CLIENT_FALLBACK = ROOT_DIR / ".claude" / "gmail-oauth-client.json"


def _resolve_oauth_client() -> Path:
    """Prefer the neutral google-oauth-client.json; fall back to the
    legacy gmail-only client (same GCP installed-app client works for
    any scope set — Gmail scopes just need to be added to the consent
    screen of whichever project owns the chosen client)."""
    if _OAUTH_CLIENT_PRIMARY.exists():
        return _OAUTH_CLIENT_PRIMARY
    if _OAUTH_CLIENT_FALLBACK.exists():
        return _OAUTH_CLIENT_FALLBACK
    return _OAUTH_CLIENT_PRIMARY  # caller errors out on missing file
_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


# ── Reader ───────────────────────────────────────────────────────────


class GmailReader:
    """Read-side Gmail adapter — scans labels and messages via the API."""

    def __init__(self, account_id: str) -> None:
        self._account_id = account_id

    def list_folders(self) -> list[str]:
        session, err = _session(self._account_id)
        if err:
            log.warning("GmailReader.list_folders: %s", err)
            return []
        resp = session.get(f"{_API_BASE}/labels")
        if resp.status_code != 200:
            return []
        return sorted(label["name"] for label in resp.json().get("labels", []))

    def scan_metadata(
        self,
        folder: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[MessageMeta]:
        session, err = _session(self._account_id)
        if err:
            raise MailboxReadError(f"GmailReader[{self._account_id}]: {err}")

        query_parts: list[str] = []
        if folder:
            query_parts.append(f"label:{folder}")
        if since is not None:
            query_parts.append(f"after:{int(since.timestamp())}")
        query = " ".join(query_parts) if query_parts else None

        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {"maxResults": 500}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token
            resp = session.get(f"{_API_BASE}/messages", params=params)
            if resp.status_code != 200:
                raise MailboxReadError(
                    f"GmailReader[{self._account_id}]: messages.list HTTP "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            for ref in data.get("messages") or ():
                meta = _fetch_metadata(session, self._account_id, ref["id"])
                if meta is not None:
                    yield meta
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def scan_deep(
        self,
        folder: str,
        limit: int = 0,
        since: datetime | None = None,
    ) -> Iterator[Message]:
        session, err = _session(self._account_id)
        if err:
            raise MailboxReadError(f"GmailReader[{self._account_id}]: {err}")

        query_parts = [f"label:{folder}"]
        if since is not None:
            query_parts.append(f"after:{int(since.timestamp())}")
        query = " ".join(query_parts)

        emitted = 0
        page_token: str | None = None
        while True:
            params: dict[str, str | int] = {"maxResults": 100, "q": query}
            if page_token:
                params["pageToken"] = page_token
            resp = session.get(f"{_API_BASE}/messages", params=params)
            if resp.status_code != 200:
                raise MailboxReadError(
                    f"GmailReader[{self._account_id}]: messages.list HTTP "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            for ref in data.get("messages") or ():
                msg = _fetch_full(session, self._account_id, ref["id"])
                if msg is None:
                    continue
                yield msg
                emitted += 1
                if limit and emitted >= limit:
                    return
            page_token = data.get("nextPageToken")
            if not page_token:
                break


def _fetch_metadata(session, account_id: str, msg_id: str) -> MessageMeta | None:
    resp = session.get(
        f"{_API_BASE}/messages/{msg_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Subject", "Date", "In-Reply-To", "Message-ID"],
        },
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers") or ()}
    label_ids = data.get("labelIds") or []
    folder = label_ids[0] if label_ids else "INBOX"
    return MessageMeta(
        id=msg_id,
        account_id=account_id,
        folder=folder,
        from_addr=headers.get("From", ""),
        to_addrs=tuple(t.strip() for t in (headers.get("To") or "").split(",") if t.strip()),
        subject=headers.get("Subject", ""),
        date=_parse_internal_date(data.get("internalDate")),
        size_bytes=int(data.get("sizeEstimate") or 0),
        in_reply_to=headers.get("In-Reply-To"),
        message_id=headers.get("Message-ID"),
    )


def _fetch_full(session, account_id: str, msg_id: str) -> Message | None:
    resp = session.get(f"{_API_BASE}/messages/{msg_id}", params={"format": "full"})
    if resp.status_code != 200:
        return None
    data = resp.json()
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers") or ()}
    label_ids = data.get("labelIds") or []
    folder = label_ids[0] if label_ids else "INBOX"
    meta = MessageMeta(
        id=msg_id,
        account_id=account_id,
        folder=folder,
        from_addr=headers.get("From", ""),
        to_addrs=tuple(t.strip() for t in (headers.get("To") or "").split(",") if t.strip()),
        subject=headers.get("Subject", ""),
        date=_parse_internal_date(data.get("internalDate")),
        size_bytes=int(data.get("sizeEstimate") or 0),
        in_reply_to=headers.get("In-Reply-To"),
        message_id=headers.get("Message-ID"),
    )
    body_text = _extract_text_body(data.get("payload") or {})
    return Message(meta=meta, body_text=body_text)


def _parse_internal_date(internal_ms: str | None) -> datetime:
    if not internal_ms:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromtimestamp(int(internal_ms) / 1000)
    except Exception:  # noqa: BLE001
        return datetime.fromtimestamp(0)


def _extract_text_body(payload: dict) -> str:
    """Walk Gmail-API payload tree, return first text/plain part decoded."""
    import base64

    if payload.get("mimeType") == "text/plain":
        body = payload.get("body") or {}
        data = body.get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return ""
    for part in payload.get("parts") or ():
        out = _extract_text_body(part)
        if out:
            return out
    return ""


class GmailFilter:
    """Apply mail filter rules via the Gmail API."""

    def __init__(self, account_id: str) -> None:
        self._account_id = account_id

    def apply(self, rule: FilterRule, *, dry_run: bool = False) -> ApplyResult:
        if rule.action.kind != "move":
            return ApplyResult(
                success=False,
                message=f"gmail-api: action.kind={rule.action.kind!r} not yet implemented (move only).",
                dry_run=dry_run,
            )

        try:
            session, err = _session(self._account_id)
            if err:
                return ApplyResult(success=False, message=f"gmail-api: {err}", dry_run=dry_run)

            label_name = rule.action.target.replace("INBOX/", "").strip()
            label_id = _ensure_label(session, label_name)
            if not label_id:
                return ApplyResult(
                    success=False,
                    message=f"gmail-api: could not find/create label {label_name!r}",
                    dry_run=dry_run,
                )

            from_criteria = " OR ".join(rule.condition.from_addrs)
            filter_body = {
                "criteria": {"from": from_criteria},
                "action": {"addLabelIds": [label_id], "removeLabelIds": ["INBOX"]},
            }

            if dry_run:
                return ApplyResult(
                    success=True,
                    message=(
                        f"gmail-api: would POST filter "
                        f"({from_criteria} → {label_name})"
                    ),
                    dry_run=True,
                )

            resp = session.post(f"{_API_BASE}/settings/filters", json=filter_body)
            if resp.status_code != 200:
                return ApplyResult(
                    success=False,
                    message=f"gmail-api: HTTP {resp.status_code}: {resp.text[:200]}",
                    dry_run=dry_run,
                )

            return ApplyResult(
                success=True,
                rule_id=resp.json().get("id"),
                message=f"gmail-api: filter created ({from_criteria} → {label_name})",
            )
        except Exception as e:  # noqa: BLE001
            log.exception("GmailFilter.apply failed for %s", self._account_id)
            return ApplyResult(
                success=False,
                message=f"gmail-api: {type(e).__name__}: {e}",
                dry_run=dry_run,
            )

    def list_existing(self) -> list[FilterRule]:
        session, err = _session(self._account_id)
        if err:
            log.warning("GmailFilter.list_existing: %s", err)
            return []
        resp = session.get(f"{_API_BASE}/settings/filters")
        if resp.status_code == 204:
            return []
        # Translation back to domain.mail.FilterRule is lossy + not yet
        # needed by callers; return empty to avoid lying about content.
        return []


# ── OAuth — thin wrappers over core.google_oauth ─────────────────────
#
# The OAuth dance (consent flow, JSON token cache, refresh, legacy-pickle
# migration) lives in core/google_oauth.py — shared with collectors/gmeet.py.
# `_app()` is rebuilt per call so tests that monkeypatch `_OAUTH_CLIENT`
# still take effect.


def _app() -> OAuthApp:
    return OAuthApp(
        client_file=_resolve_oauth_client(),
        scopes=tuple(_SCOPES),
        token_prefix="gmail-token",
        bootstrap_cmd="wiki gmail-auth",
        service_label="Gmail",
    )


def _session(account_id: str):
    """Returns (session, error_msg). Session is a google-auth AuthorizedSession."""
    return google_oauth.session(_app(), account_id)


def _token_path(account_id: str) -> Path:
    """Token cache: `<.wiki>/state/gmail-token-<id>.json`."""
    return google_oauth.token_path(_app(), account_id)


def gmail_auth_bootstrap(account_id: str) -> tuple[bool, str]:
    """Run the installed-app OAuth flow once. Persist token + return (ok, message).

    Operator pre-condition: place OAuth client_secret.json at the path
    reported by `_resolve_oauth_client()`. The flow opens a local-loopback browser
    for the consent screen. Called from `wiki gmail-auth <id>`.
    """
    return google_oauth.bootstrap(_app(), account_id)


def _ensure_label(session, label_name: str) -> str | None:
    resp = session.get(f"{_API_BASE}/labels")
    if resp.status_code != 200:
        return None
    for label in resp.json().get("labels", []):
        if label["name"] == label_name:
            return label["id"]
    resp = session.post(
        f"{_API_BASE}/labels",
        json={
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("id")
