"""Gmail filter adapter — server-side rules via Gmail API.

S02 ports the existing Gmail-filter creation from
`scripts/thunderbird-rules.py` into the adapter shape so
`execute-suggestions.py` can dispatch via `resolve_filter()` uniformly
for all three filter backends.

S03 will add `GmailReader` (read-side scanning of Gmail labels), a
proper OAuth bootstrap subcommand (`wiki gmail-auth`), and migrate the
token cache from pickle → JSON at `<.wiki>/state/gmail-token-<id>.json`.
For S02, the existing pickle-based token at `<vault>/.claude/gmail-token-<id>.pickle`
is preserved so live setups keep working.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from adapters.mailbox.base import ApplyResult
from config import ROOT_DIR
from domain.mail import FilterRule

log = logging.getLogger(__name__)


_OAUTH_CLIENT = ROOT_DIR / ".claude" / "gmail-oauth-client.json"
_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


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


def _credentials(account_id: str):
    """Load + refresh OAuth credentials. Returns (creds, error_msg).

    Token cache at `<vault>/.claude/gmail-token-<id>.pickle` (legacy
    location, S02 preserves; S03 migrates to JSON in `.wiki/state/`).
    """
    import pickle  # noqa: S403  own OAuth tokens, not untrusted data

    from google.auth.transport.requests import Request

    token_file = ROOT_DIR / ".claude" / f"gmail-token-{account_id}.pickle"

    creds = None
    if token_file.exists():
        try:
            with open(token_file, "rb") as f:
                creds = pickle.load(f)  # noqa: S301
        except Exception as e:  # noqa: BLE001
            return None, f"Could not read token file {token_file}: {e}"

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:  # noqa: BLE001
                return None, f"Token refresh failed: {e}"
        else:
            return None, _bootstrap_hint(account_id)

        try:
            with open(token_file, "wb") as f:
                pickle.dump(creds, f)  # noqa: S301
        except Exception as e:  # noqa: BLE001
            log.warning("Could not persist refreshed Gmail token to %s: %s", token_file, e)

    return creds, None


def _bootstrap_hint(account_id: str) -> str:
    return (
        f"Gmail OAuth credentials missing for {account_id!r}. "
        f"Place client_secret.json at {_OAUTH_CLIENT} and run "
        f"`wiki gmail-auth {account_id}` (S03 will provide this subcommand). "
        f"For now: run any retroactive Gmail action once via the legacy "
        f"path to seed the token cache."
    )


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
