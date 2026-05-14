"""Shared Google OAuth helper — installed-app flow + token cache.

One `OAuthApp` describes a single Google-API integration (its client-secret
file, scopes, token-cache prefix, bootstrap command). The functions here run
the consent flow, persist the token, refresh it, and hand back an
`AuthorizedSession`. Each consumer module (`adapters/mailbox/gmail.py`,
`collectors/gmeet.py`) builds its own `OAuthApp` and delegates here so the
token-refresh / persist / legacy-migration logic lives in exactly one place.

Token cache: `<.wiki>/state/<token_prefix>-<account_id>.json`.
Legacy pickle migration: `<vault>/.claude/<token_prefix>-<account_id>.pickle`
(gmail's pre-S03 format) is read once and rewritten as JSON. For integrations
that never had a pickle (gmeet), the migration branch is a harmless no-op.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from core.paths import ROOT_DIR, STATE_DIR

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OAuthApp:
    """Static identity of one OAuth-using integration."""

    client_file: Path
    """`<vault>/.claude/<name>-oauth-client.json` — operator-provided installed-app
    client secret. The same GCP client works for any scope set."""

    scopes: tuple[str, ...]
    """OAuth scopes requested during consent."""

    token_prefix: str
    """Token cache → `state/<token_prefix>-<account_id>.json`. Also the legacy
    pickle prefix under `.claude/`."""

    bootstrap_cmd: str
    """Operator-facing command that runs the consent flow, e.g. `wiki gmail-auth`."""

    service_label: str
    """Human label for hint messages, e.g. `Gmail`."""


def token_path(app: OAuthApp, account_id: str) -> Path:
    """JSON token cache path for this app + account."""
    return STATE_DIR / f"{app.token_prefix}-{account_id}.json"


def _legacy_pickle_path(app: OAuthApp, account_id: str) -> Path:
    """Pre-S03 pickle location (gmail only — inert for newer integrations)."""
    return ROOT_DIR / ".claude" / f"{app.token_prefix}-{account_id}.pickle"


def _persist(creds, token_file: Path, scopes: tuple[str, ...]) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or scopes),
    }
    if hasattr(creds, "expiry") and creds.expiry is not None:
        payload["expiry"] = creds.expiry.isoformat()
    token_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def bootstrap_hint(app: OAuthApp, account_id: str) -> str:
    """Operator-facing message when no usable credentials exist yet."""
    return (
        f"{app.service_label} OAuth credentials missing for {account_id!r}. "
        f"Place an OAuth client_secret.json at {app.client_file}, then run "
        f"`{app.bootstrap_cmd} {account_id}`. The token cache will be written to "
        f"{token_path(app, account_id)}."
    )


def credentials(app: OAuthApp, account_id: str):
    """Load + refresh OAuth credentials. Returns (creds, error_msg).

    Reads the JSON token cache; falls back to a legacy pickle (gmail pre-S03)
    and migrates it to JSON on first successful load. Refreshes expired
    credentials in place. Returns (None, hint) when no usable token exists.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = token_path(app, account_id)

    creds = None
    if token_file.exists():
        try:
            data = json.loads(token_file.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(data, list(app.scopes))
        except Exception as e:  # noqa: BLE001
            log.warning("Bad JSON token at %s: %s — will re-bootstrap", token_file, e)
            creds = None

    if creds is None:
        legacy = _legacy_pickle_path(app, account_id)
        if legacy.exists():
            import pickle  # noqa: S403  own OAuth tokens

            try:
                with open(legacy, "rb") as f:
                    creds = pickle.load(f)  # noqa: S301
                _persist(creds, token_file, app.scopes)
                log.info("Migrated %s token from %s → %s",
                         app.service_label, legacy, token_file)
            except Exception as e:  # noqa: BLE001
                log.warning("Could not migrate legacy pickle %s: %s", legacy, e)
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _persist(creds, token_file, app.scopes)
            except Exception as e:  # noqa: BLE001
                return None, f"Token refresh failed: {e}"
        else:
            return None, bootstrap_hint(app, account_id)

    return creds, None


def session(app: OAuthApp, account_id: str):
    """Returns (AuthorizedSession, None) or (None, error_msg)."""
    try:
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        return None, "google-auth not installed (uv sync should have it)"

    creds, err = credentials(app, account_id)
    if err:
        return None, err
    return AuthorizedSession(creds), None


def bootstrap(app: OAuthApp, account_id: str) -> tuple[bool, str]:
    """Run the installed-app OAuth consent flow once. Persist token + return (ok, message).

    Pre-condition: the operator has placed an installed-app client secret at
    `app.client_file`. Opens a local-loopback browser for the consent screen.
    """
    if not app.client_file.exists():
        return False, (
            f"Missing OAuth client config: {app.client_file}\n"
            "Create an installed-app OAuth client at "
            "https://console.cloud.google.com/apis/credentials, "
            "download the JSON, save it to that path, and re-run."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(app.client_file), list(app.scopes)
        )
        creds = flow.run_local_server(port=0)
        _persist(creds, token_path(app, account_id), app.scopes)
    except Exception as e:  # noqa: BLE001
        return False, f"OAuth flow failed: {type(e).__name__}: {e}"
    return True, f"Token cached at {token_path(app, account_id)}"
