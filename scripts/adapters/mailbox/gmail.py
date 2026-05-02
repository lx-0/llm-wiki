"""Gmail Reader + Filter adapters via Gmail API.

S02 shipped GmailFilter (server-side rule creation).
S03 adds GmailReader (read-side label/message scanning) plus an OAuth
bootstrap UX via `wiki gmail-auth <account-id>` and a JSON token cache
at `<.wiki>/state/gmail-token-<id>.json`.

OAuth client secret lives at `<vault>/.claude/gmail-oauth-client.json`
(per-install, gitignored). Operator places the file once after creating
an OAuth client at https://console.cloud.google.com.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator

from adapters.mailbox.base import ApplyResult
from config import ROOT_DIR, STATE_DIR
from domain.mail import FilterRule, Message, MessageMeta

log = logging.getLogger(__name__)


_OAUTH_CLIENT = ROOT_DIR / ".claude" / "gmail-oauth-client.json"
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
            log.warning("GmailReader.scan_metadata: %s", err)
            return

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
                log.warning("Gmail messages.list HTTP %s: %s", resp.status_code, resp.text[:200])
                return
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
            log.warning("GmailReader.scan_deep: %s", err)
            return

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
                return
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


# ── Session + token cache ────────────────────────────────────────────


def _session(account_id: str):
    """Returns (session, error_msg). Session is google-auth AuthorizedSession."""
    try:
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        return None, "google-auth-oauthlib not installed (uv sync should have it)"

    creds, err = _credentials(account_id)
    if err:
        return None, err
    return AuthorizedSession(creds), None


def _token_path(account_id: str) -> Path:
    """Token cache lives at `<.wiki>/state/gmail-token-<id>.json` (S03+).

    Migrated from legacy pickle at `<vault>/.claude/gmail-token-<id>.pickle`
    by `gmail_auth_bootstrap` on first run after upgrade.
    """
    return STATE_DIR / f"gmail-token-{account_id}.json"


def _legacy_pickle_path(account_id: str) -> Path:
    return ROOT_DIR / ".claude" / f"gmail-token-{account_id}.pickle"


def _credentials(account_id: str):
    """Load + refresh OAuth credentials. Returns (creds, error_msg).

    Token cache at `<.wiki>/state/gmail-token-<id>.json`. If missing,
    falls back to legacy pickle at `<vault>/.claude/gmail-token-<id>.pickle`
    and migrates on first successful load.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = _token_path(account_id)

    creds = None
    if token_file.exists():
        try:
            data = json.loads(token_file.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(data, _SCOPES)
        except Exception as e:  # noqa: BLE001
            log.warning("Bad JSON token at %s: %s — will re-bootstrap", token_file, e)
            creds = None

    if creds is None:
        # Try legacy pickle migration.
        legacy = _legacy_pickle_path(account_id)
        if legacy.exists():
            import pickle  # noqa: S403  own OAuth tokens

            try:
                with open(legacy, "rb") as f:
                    creds = pickle.load(f)  # noqa: S301
                _persist(creds, token_file)
                log.info("Migrated Gmail token from %s → %s", legacy, token_file)
            except Exception as e:  # noqa: BLE001
                log.warning("Could not migrate legacy pickle %s: %s", legacy, e)
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _persist(creds, token_file)
            except Exception as e:  # noqa: BLE001
                return None, f"Token refresh failed: {e}"
        else:
            return None, _bootstrap_hint(account_id)

    return creds, None


def _persist(creds, token_file: Path) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or _SCOPES),
    }
    if hasattr(creds, "expiry") and creds.expiry is not None:
        payload["expiry"] = creds.expiry.isoformat()
    token_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _bootstrap_hint(account_id: str) -> str:
    return (
        f"Gmail OAuth credentials missing for {account_id!r}. "
        f"Place an OAuth client_secret.json at {_OAUTH_CLIENT}, then run "
        f"`wiki gmail-auth {account_id}`. The token cache will be written to "
        f"{_token_path(account_id)}."
    )


# ── OAuth bootstrap (called from `wiki gmail-auth <id>`) ─────────────


def gmail_auth_bootstrap(account_id: str) -> tuple[bool, str]:
    """Run the installed-app OAuth flow once. Persist token + return (ok, message).

    Operator pre-condition: place OAuth client_secret.json at the path
    reported by `_OAUTH_CLIENT`. The flow opens a local-loopback browser
    for the consent screen.
    """
    if not _OAUTH_CLIENT.exists():
        return False, (
            f"Missing OAuth client config: {_OAUTH_CLIENT}\n"
            "Create an installed-app OAuth client at "
            "https://console.cloud.google.com/apis/credentials, "
            "download the JSON, save it to that path, and re-run."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(_OAUTH_CLIENT), _SCOPES)
        creds = flow.run_local_server(port=0)
        _persist(creds, _token_path(account_id))
    except Exception as e:  # noqa: BLE001
        return False, f"OAuth flow failed: {type(e).__name__}: {e}"
    return True, f"Token cached at {_token_path(account_id)}"


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
