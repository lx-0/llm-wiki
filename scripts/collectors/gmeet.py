"""Gmeet Collector — pulls Google Meet / Gemini transcripts from Google Drive.

Multi-tenant: per-account `gmeet:` sub-block under `CONFIG.personal.accounts.<id>`,
discriminated by `kind: gmeet-api` (mirrors the email Reader/Filter pattern). When
Google Meet records a meeting with Gemini, it drops Google Docs into the Drive
"Meet Recordings" folder — a transcript Doc (already speaker-diarised) and/or a
"Notes by Gemini" Doc. This collector exports those Docs as markdown into
`raw/transcripts/gmeet/`, looping over every configured account each run.

Drive-only wedge. The Meet REST API (`conferenceRecords`) was evaluated and
deferred — see `.ytstack/backlog/gmeet-collector.md`: it is organizer-only,
its records expire 30 days after the conference, and transcript-entry speakers
are resource names needing extra resolution calls. The Drive Doc export has
none of those limits and is already diarised.

Auth (per account):
- OAuth via `core/google_oauth.py` (shared with `adapters/mailbox/gmail.py`).
  Scope `drive.meet.readonly` — the dedicated narrow scope for files created
  or edited by Google Meet. Bootstrapped once per account via
  `wiki gmeet-auth <account-id>` (`<account-id>` matches the key under
  `personal.accounts`); token cache at `state/gmeet-token-<account-id>.json`.
- Client secret: `<vault>/.claude/google-oauth-client.json`, falling back to
  the existing `.claude/gmail-oauth-client.json` (same GCP installed-app
  client works for any scope and any user account; tokens are cached
  separately per user).
- An account with no `gmeet:` sub-block, or with the sub-block but no
  cached token, is silently skipped (graceful-agnostic) — the rest of the
  loop still runs.

State:
- `state/gmeet-state.json` carries `{<account_id>: {last_seen_ts: ISO 8601}}`.
  Incremental runs query Drive per account for Docs with `createdTime` greater
  than its watermark; the highest `createdTime` seen during a successful
  per-account scan becomes the new watermark *for that account only*. A failed
  account leaves its watermark untouched (mirrors the email-collector
  failure-vs-empty discipline).
- Skip-existing is keyed on the Drive file id: any file under
  `raw/transcripts/gmeet/` whose name ends in `--<short-id>.md` is considered
  already ingested. Drive file ids are globally unique, so the flat output
  folder works across accounts.

Shape note: one Drive Doc → one markdown file. Meet emits up to two Docs per
meeting (transcript + notes); grouping them into a single article is a
deferred refinement (needs live data to pin Google's locale-dependent Doc
naming) — see the backlog file.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

from collectors.base import CollectorSpec, RunResult, register
from core import google_oauth
from core.config import CONFIG
from core.google_oauth import OAuthApp
from core.paths import ROOT_DIR, STATE_DIR
from core.utils import load_json_state, now_iso, save_json_state

log = logging.getLogger(__name__)


# ── API constants ────────────────────────────────────────────────────

_DRIVE_BASE = "https://www.googleapis.com/drive/v3"
_DRIVE_DOC_MIME = "application/vnd.google-apps.document"
_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
# Markdown export is officially supported for Google Docs; text/plain is the
# fallback for the rare Doc that rejects markdown export.
_EXPORT_MIME = "text/markdown"
_EXPORT_FALLBACK_MIME = "text/plain"

# Scope: the dedicated narrow scope for Drive files created/edited by Meet.
_SCOPES = ("https://www.googleapis.com/auth/drive.meet.readonly",)

# Client secret — prefer a neutral filename, fall back to gmail's (same GCP
# installed-app client works for any scope set).
_OAUTH_CLIENT_PRIMARY = ROOT_DIR / ".claude" / "google-oauth-client.json"
_OAUTH_CLIENT_FALLBACK = ROOT_DIR / ".claude" / "gmail-oauth-client.json"


# ── Output shape ─────────────────────────────────────────────────────

_OUTPUT_SUBFOLDER = "raw/transcripts/gmeet"
_STATE_FILE = STATE_DIR / "gmeet-state.json"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHORT_ID_LEN = 12

# Best-effort classification of a Meet-generated Doc by its title suffix.
# EN + DE — extend as more locales surface. `unknown` is a safe default:
# the Doc is still ingested verbatim, just under a generic heading.
_KIND_TRANSCRIPT_RE = re.compile(r"\b(transcript|transkript)\b", re.IGNORECASE)
_KIND_NOTES_RE = re.compile(r"\b(notes by gemini|gemini[- ]?notes?|notizen)\b", re.IGNORECASE)
# Trailing " - <suffix>" segment stripped to derive the meeting title.
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[-–—]\s*(transcript|transkript|notes by gemini|gemini[- ]?notes?|"
    r"notizen von gemini|gemini-notizen)\s*$",
    re.IGNORECASE,
)


def _slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _short_id(file_id: str) -> str:
    """Stable short id from a Drive file id (used for skip-existing + filename)."""
    alnum = re.sub(r"[^A-Za-z0-9]", "", file_id)
    return alnum[:_SHORT_ID_LEN] or file_id[:_SHORT_ID_LEN]


def _classify_doc(name: str) -> str:
    """`transcript` | `notes` | `unknown` — best-effort, by title suffix."""
    if _KIND_TRANSCRIPT_RE.search(name):
        return "transcript"
    if _KIND_NOTES_RE.search(name):
        return "notes"
    return "unknown"


def _meeting_title(name: str) -> str:
    """Strip a trailing Meet/Gemini suffix to get the bare meeting title."""
    return _TITLE_SUFFIX_RE.sub("", name).strip() or name


def _resolve_oauth_client() -> Path:
    """Prefer the neutral client file; fall back to gmail's. Returns the primary
    path even when neither exists — `google_oauth.bootstrap` reports it clearly."""
    if _OAUTH_CLIENT_PRIMARY.exists():
        return _OAUTH_CLIENT_PRIMARY
    if _OAUTH_CLIENT_FALLBACK.exists():
        return _OAUTH_CLIENT_FALLBACK
    return _OAUTH_CLIENT_PRIMARY


def _app() -> OAuthApp:
    return OAuthApp(
        client_file=_resolve_oauth_client(),
        scopes=_SCOPES,
        token_prefix="gmeet-token",
        bootstrap_cmd="wiki gmeet-auth",
        service_label="Google Meet",
    )


def gmeet_auth_bootstrap(account_id: str) -> tuple[bool, str]:
    """Run the installed-app OAuth flow once for one account. Called from
    `wiki gmeet-auth <account-id>`. The account-id should match a key under
    `personal.accounts.<id>` whose body has a `gmeet:` sub-block — but the
    bootstrap itself is config-agnostic; it just persists a token under
    that id. Opens a local-loopback browser for the consent screen."""
    return google_oauth.bootstrap(_app(), account_id)


# ── Per-account resolution ───────────────────────────────────────────

@dataclass(frozen=True)
class _GmeetAccount:
    """Resolved gmeet config for one `personal.accounts.<id>` entry."""
    account_id: str
    drive_folder_id: str
    drive_folder_name: str
    since: str | None
    max_per_run: int


def _resolve_gmeet_accounts() -> list[_GmeetAccount]:
    """Iterate `CONFIG.personal.accounts`, return the ones with a
    `gmeet:` sub-block whose `kind == "gmeet-api"`. Mirrors the
    `resolve_reader` / `resolve_filter` dispatch on `kind`. Unknown
    kinds are silently skipped (graceful-agnostic)."""
    out: list[_GmeetAccount] = []
    accounts = CONFIG.personal.accounts or {}
    default_max = CONFIG.limits.gmeet_max_per_run
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        block = body.get("gmeet")
        if not isinstance(block, dict) or block.get("kind") != "gmeet-api":
            continue
        per_acct_max = block.get("max_per_run")
        out.append(_GmeetAccount(
            account_id=aid,
            drive_folder_id=block.get("drive_folder_id") or "",
            drive_folder_name=block.get("drive_folder_name") or "Meet Recordings",
            since=block.get("since") or None,
            max_per_run=per_acct_max if per_acct_max is not None else default_max,
        ))
    return out


# ── HTTP client (inline — Drive API over the shared OAuth session) ────

class GmeetAPIError(RuntimeError):
    """Raised on non-recoverable Drive API failures (401, persistent 5xx, schema)."""


@dataclass
class _DriveClient:
    """Thin Drive v3 wrapper over a google-auth AuthorizedSession.

    Retry shape mirrors `collectors/jamie.py._JamieClient._get`: retry once on
    network error / 429 / 5xx, raise on 401 / persistent failure.
    """

    session: Any                 # google.auth.transport.requests.AuthorizedSession
    timeout_s: float

    def _get(self, url: str, *, params: dict | None = None, expect_json: bool = True) -> Any:
        for attempt in (1, 2):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout_s)
            except Exception as e:  # noqa: BLE001  network layer — requests/urllib3
                if attempt == 2:
                    raise GmeetAPIError(f"network failure on GET {url}: {type(e).__name__}: {e}") from e
                log.warning("gmeet GET %s: %s — retrying once in 5s", url, type(e).__name__)
                time.sleep(5)
                continue

            if r.status_code == 401:
                raise GmeetAPIError(
                    "401 from Drive — token invalid or scope not granted. "
                    "Re-run `wiki gmeet-auth`."
                )
            if r.status_code == 403:
                # 403 is non-recoverable here (scope/permission/export-size) —
                # surface the Drive message rather than retrying blindly.
                raise GmeetAPIError(f"403 on GET {url}: {r.text[:200]}")
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                if attempt == 2:
                    raise GmeetAPIError(f"429 on GET {url} after retry (waited {wait}s)")
                log.warning("gmeet GET %s: 429 — sleeping %ds before retry", url, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                if attempt == 2:
                    raise GmeetAPIError(f"persistent {r.status_code} on GET {url}: {r.text[:200]}")
                log.warning("gmeet GET %s: %d — retrying once in 5s", url, r.status_code)
                time.sleep(5)
                continue
            if r.status_code != 200:
                raise GmeetAPIError(f"unexpected {r.status_code} on GET {url}: {r.text[:200]}")

            return r.json() if expect_json else r.text

        raise GmeetAPIError(f"unreachable: exhausted retries on GET {url}")

    def resolve_folder_id(self, name: str) -> str | None:
        """Find a folder by exact name. Returns None if not found or the narrow
        scope blocks the name search (caller falls back to a clear error)."""
        q = (
            f"name = '{name.replace(chr(39), chr(92) + chr(39))}' "
            f"and mimeType = '{_DRIVE_FOLDER_MIME}' and trashed = false"
        )
        try:
            payload = self._get(
                f"{_DRIVE_BASE}/files",
                params={"q": q, "fields": "files(id,name)", "pageSize": 10},
            )
        except GmeetAPIError as e:
            log.warning("gmeet: folder name-search failed (%s) — set drive_folder_id explicitly", e)
            return None
        files = payload.get("files") or []
        if not files:
            return None
        return files[0].get("id")

    def list_docs(
        self, folder_id: str, *, since: str | None = None, limit: int | None = None,
    ) -> Iterator[dict]:
        """Yield Google-Doc file stubs in `folder_id`, oldest first.

        Stub fields: id, name, createdTime, modifiedTime, webViewLink.
        Paginates while `nextPageToken` is non-empty; stops after `limit`.
        """
        q_parts = [
            f"'{folder_id}' in parents",
            f"mimeType = '{_DRIVE_DOC_MIME}'",
            "trashed = false",
        ]
        if since:
            q_parts.append(f"createdTime > '{since}'")
        q = " and ".join(q_parts)

        seen = 0
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": q,
                "fields": "nextPageToken,files(id,name,createdTime,modifiedTime,webViewLink)",
                "orderBy": "createdTime",
                "pageSize": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get(f"{_DRIVE_BASE}/files", params=params)
            if not isinstance(payload, dict):
                raise GmeetAPIError(f"files.list returned {type(payload).__name__}, expected dict")
            for item in payload.get("files") or []:
                yield item
                seen += 1
                if limit and seen >= limit:
                    return
            page_token = payload.get("nextPageToken")
            if not page_token:
                return

    def export_doc(self, file_id: str) -> str:
        """Export a Google Doc as markdown text. Falls back to text/plain."""
        url = f"{_DRIVE_BASE}/files/{file_id}/export"
        try:
            return self._get(url, params={"mimeType": _EXPORT_MIME}, expect_json=False)
        except GmeetAPIError as e:
            log.warning("gmeet: markdown export failed for %s (%s) — trying text/plain", file_id, e)
            return self._get(url, params={"mimeType": _EXPORT_FALLBACK_MIME}, expect_json=False)


# ── Rendering ────────────────────────────────────────────────────────

_HEADING_BY_KIND = {
    "transcript": "## Transcript",
    "notes": "## Summary",
    "unknown": "## Notes",
}


def _render_markdown(doc: dict, exported: str, *, account_id: str, input_source: str) -> str:
    """One markdown file per Drive Doc. Substrate-uniform frontmatter + body."""
    file_id = doc.get("id") or "unknown"
    name = doc.get("name") or file_id
    created = doc.get("createdTime")
    kind = _classify_doc(name)
    title = _meeting_title(name)

    front: dict[str, Any] = {
        "type": "transcript",
        "source": "gmeet",
        "meeting_id": _short_id(file_id),
        "title": title,
        "doc_kind": kind,
        "started_at": created,
        "drive_doc_id": file_id,
        "drive_doc_name": name,
        "drive_url": doc.get("webViewLink"),
        "tags": ["gmeet", "meeting"],
        "ingested_at": now_iso(),
        "input_source": input_source,
        "account_id": account_id,
    }
    front = {k: v for k, v in front.items() if v not in (None, [], "")}
    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    header_bits = []
    if created:
        header_bits.append(str(created)[:10])
    header_bits.append(kind)

    parts: list[str] = [
        f"---\n{fm}\n---",
        "",
        f"# {title}",
        "",
        f"_{' · '.join(header_bits)}_",
        "",
        _HEADING_BY_KIND.get(kind, "## Notes"),
        "",
        exported.strip(),
        "",
    ]
    return "\n".join(parts) + "\n"


# ── Collector ────────────────────────────────────────────────────────

@register
class GmeetCollector:
    SPEC = CollectorSpec(
        name="gmeet",
        output_subfolder=_OUTPUT_SUBFOLDER,
        piggyback_default=True,
        piggyback_cooldown_hours=6,
        supports_incremental=True,
        supports_account_loop=True,
    )

    def __init__(self) -> None:
        self._accounts = _resolve_gmeet_accounts()
        self._timeout_s = float(CONFIG.limits.gmeet_request_timeout_s)

    def is_configured(self) -> bool:
        """At least one account has `kind: gmeet-api` AND a bootstrapped token cache.
        Configured-but-not-bootstrapped accounts (no token) don't count — the
        piggyback should silently skip until the operator has run `wiki gmeet-auth`
        for at least one. Per-account is_configured is decided inside `run()`."""
        if not self._accounts:
            return False
        return any(
            google_oauth.token_path(_app(), a.account_id).exists()
            for a in self._accounts
        )

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self._accounts:
            log.info("GmeetCollector: no accounts with kind=gmeet-api — skipping.")
            return RunResult(message="no-op (no gmeet accounts configured)")

        all_files: list[Path] = []
        total_skipped = 0
        per_acct_messages: list[str] = []
        any_state_touched = False

        # Output dir + skip-existing set are shared across accounts (Drive file
        # ids are globally unique, the flat output folder is fine).
        output_root = ROOT_DIR / self.SPEC.output_subfolder
        already_present: set[str] = set()
        if output_root.exists():
            already_present = {
                p.stem.rsplit("--", 1)[-1]
                for p in output_root.glob("*.md")
                if "--" in p.stem
            }

        state = load_json_state(_STATE_FILE)
        # Migrate the pre-multi-tenant flat shape ({last_seen_ts: ...}) into a
        # default per-account bucket so a clean lift doesn't lose the watermark.
        if "last_seen_ts" in state and not any(
            isinstance(v, dict) and "last_seen_ts" in v for v in state.values()
        ):
            legacy = state.pop("last_seen_ts")
            state.setdefault("default", {})["last_seen_ts"] = legacy
            log.info("GmeetCollector: migrated legacy flat state → state['default']")

        for acct in self._accounts:
            try:
                msg, files, skipped, state_touched = self._run_one_account(
                    acct,
                    state=state,
                    already_present=already_present,
                    dry_run=dry_run,
                    incremental=incremental,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("GmeetCollector[%s]: unexpected", acct.account_id)
                per_acct_messages.append(f"{acct.account_id}: ERROR {type(e).__name__}: {e}")
                continue
            all_files.extend(files)
            total_skipped += skipped
            per_acct_messages.append(f"{acct.account_id}: {msg}")
            # New filenames added this account count toward the next account's
            # skip-set (rare collision case: same Doc shared with two accounts).
            already_present.update(_short_id(p.stem.rsplit("--", 1)[-1]) for p in files)
            any_state_touched = any_state_touched or state_touched

        if not dry_run and any_state_touched:
            save_json_state(_STATE_FILE, state)

        return RunResult(
            files_written=tuple(all_files),
            files_skipped=total_skipped,
            state_keys_touched=tuple(a.account_id for a in self._accounts) if any_state_touched else (),
            message=" · ".join(per_acct_messages) or "no-op",
        )

    def _run_one_account(
        self,
        acct: _GmeetAccount,
        *,
        state: dict,
        already_present: set[str],
        dry_run: bool,
        incremental: bool,
    ) -> tuple[str, list[Path], int, bool]:
        """Run one account's scan. Returns (one-line message, files, skipped, state_touched).
        Mutates `state[acct.account_id]['last_seen_ts']` only on a successful scan
        that wrote files — failures leave the watermark untouched."""
        sess, err = google_oauth.session(_app(), acct.account_id)
        if err:
            return f"auth: {err}", [], 0, False

        client = _DriveClient(session=sess, timeout_s=self._timeout_s)

        folder_id = acct.drive_folder_id or client.resolve_folder_id(acct.drive_folder_name)
        if not folder_id:
            return (
                f"folder {acct.drive_folder_name!r} not found — set "
                f"personal.accounts.{acct.account_id}.gmeet.drive_folder_id "
                "(copy it from the folder URL)"
            ), [], 0, False

        per_acct_state = state.get(acct.account_id) or {}
        since = per_acct_state.get("last_seen_ts") if incremental else acct.since

        log.info(
            "GmeetCollector[%s]: listing Docs (folder=%s, since=%s, limit=%d)",
            acct.account_id, folder_id, since or "—", acct.max_per_run,
        )

        try:
            stubs = list(client.list_docs(folder_id, since=since, limit=acct.max_per_run))
        except GmeetAPIError as e:
            log.error("GmeetCollector[%s]: list failed: %s", acct.account_id, e)
            return f"list failed: {e}", [], 0, False

        if not stubs:
            return f"no-op (0 docs in window since={since or '—'})", [], 0, False

        files_written: list[Path] = []
        skipped = 0
        highest_created: str | None = per_acct_state.get("last_seen_ts")
        input_source = "piggyback" if not dry_run and incremental else "cli"

        for stub in stubs:
            file_id = stub.get("id")
            if not file_id:
                log.warning(
                    "GmeetCollector[%s]: list-row missing id — skipping: %r",
                    acct.account_id,
                    sorted(stub.keys()) if isinstance(stub, dict) else type(stub).__name__,
                )
                continue
            short = _short_id(file_id)
            if short in already_present:
                skipped += 1
                continue

            try:
                exported = client.export_doc(file_id)
            except GmeetAPIError as e:
                log.warning("GmeetCollector[%s]: export %s — %s", acct.account_id, file_id, e)
                continue

            md = _render_markdown(stub, exported, account_id=acct.account_id,
                                  input_source=input_source)
            name = stub.get("name") or file_id
            created = stub.get("createdTime") or ""
            date_prefix = str(created)[:10] if created else now_iso()[:10]
            fname = f"{date_prefix}--{_slugify(_meeting_title(name))}--{short}.md"
            target = (ROOT_DIR / self.SPEC.output_subfolder) / fname

            if dry_run:
                log.info("  DRY[%s]: would write %s (%d bytes)",
                         acct.account_id, target.relative_to(ROOT_DIR), len(md))
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            log.info("  [%s] wrote %s", acct.account_id, target.relative_to(ROOT_DIR))
            files_written.append(target)

            if created and (highest_created is None or str(created) > str(highest_created)):
                highest_created = str(created)

        state_touched = False
        if not dry_run and highest_created and highest_created != per_acct_state.get("last_seen_ts"):
            per_acct_state["last_seen_ts"] = highest_created
            state[acct.account_id] = per_acct_state
            state_touched = True

        return (
            f"listed {len(stubs)} · wrote {len(files_written)} · skipped {skipped}",
            files_written,
            skipped,
            state_touched,
        )
