"""Gmeet Collector — pulls Google Meet / Gemini transcripts from Google Drive.

Substrate-shaped: configured via `CONFIG.personal.gmeet` (single-tenant flat
block, like JamieConfig). When Google Meet records a meeting with Gemini, it
drops Google Docs into the Drive "Meet Recordings" folder — a transcript Doc
(already speaker-diarised) and/or a "Notes by Gemini" Doc. This collector
exports those Docs as markdown into `raw/transcripts/gmeet/`.

Drive-only wedge. The Meet REST API (`conferenceRecords`) was evaluated and
deferred — see `.ytstack/backlog/gmeet-collector.md`: it is organizer-only,
its records expire 30 days after the conference, and transcript-entry speakers
are resource names needing extra resolution calls. The Drive Doc export has
none of those limits and is already diarised.

Auth:
- OAuth via `core/google_oauth.py` (shared with `adapters/mailbox/gmail.py`).
  Scope `drive.meet.readonly` — the dedicated narrow scope for files created
  or edited by Google Meet. Bootstrapped once via `wiki gmeet-auth <id>`;
  token cache at `state/gmeet-token-<id>.json`.
- Client secret: `<vault>/.claude/google-oauth-client.json`, falling back to
  the existing `.claude/gmail-oauth-client.json` (same GCP installed-app
  client works for any scope; tokens are cached separately).
- Empty `oauth_account_id` or a missing token cache → `is_configured()`
  returns False and the collector is silently skipped (graceful-agnostic).

State:
- `state/gmeet-state.json` carries `last_seen_ts` (ISO 8601). Incremental runs
  query Drive for Docs with `createdTime` greater than it; the highest
  `createdTime` seen during a successful run becomes the new `last_seen_ts`.
- Skip-existing is keyed on the Drive file id: any file under
  `raw/transcripts/gmeet/` whose name ends in `--<short-id>.md` is considered
  already ingested.

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
    """Run the installed-app OAuth flow once. Called from `wiki gmeet-auth <id>`.

    Operator pre-condition: an installed-app client secret at
    `.claude/google-oauth-client.json` (or the gmail one). Opens a
    local-loopback browser for the consent screen.
    """
    return google_oauth.bootstrap(_app(), account_id)


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
        supports_account_loop=False,
    )

    def __init__(self) -> None:
        gmeet_cfg = CONFIG.personal.gmeet
        self._account_id = gmeet_cfg.oauth_account_id or ""
        self._folder_id = gmeet_cfg.drive_folder_id or ""
        self._folder_name = gmeet_cfg.drive_folder_name or "Meet Recordings"
        self._configured_since = gmeet_cfg.since or None
        self._max_per_run = (
            gmeet_cfg.max_per_run
            if gmeet_cfg.max_per_run is not None
            else CONFIG.limits.gmeet_max_per_run
        )
        self._timeout_s = float(CONFIG.limits.gmeet_request_timeout_s)

    def is_configured(self) -> bool:
        """Configured = an oauth_account_id is set AND its token cache exists.
        A set account-id without a bootstrapped token is treated as not yet
        configured — the piggyback skips, the CLI prints a hint."""
        if not self._account_id:
            return False
        return google_oauth.token_path(_app(), self._account_id).exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self._account_id:
            log.info("GmeetCollector: oauth_account_id unset — skipping.")
            return RunResult(message="no-op (gmeet oauth_account_id unset)")

        sess, err = google_oauth.session(_app(), self._account_id)
        if err:
            log.info("GmeetCollector: not authorised — %s", err)
            return RunResult(message=f"no-op (gmeet auth: {err})")

        client = _DriveClient(session=sess, timeout_s=self._timeout_s)

        folder_id = self._folder_id or client.resolve_folder_id(self._folder_name)
        if not folder_id:
            msg = (
                f"folder {self._folder_name!r} not found — set "
                "CONFIG.personal.gmeet.drive_folder_id (copy it from the folder URL)"
            )
            log.error("GmeetCollector: %s", msg)
            return RunResult(message=msg)

        state = load_json_state(_STATE_FILE)
        since = state.get("last_seen_ts") if incremental else self._configured_since

        log.info(
            "GmeetCollector: listing Docs (folder=%s, since=%s, limit=%d)",
            folder_id, since or "—", self._max_per_run,
        )

        try:
            stubs = list(client.list_docs(folder_id, since=since, limit=self._max_per_run))
        except GmeetAPIError as e:
            log.error("GmeetCollector: list failed: %s", e)
            return RunResult(message=f"list failed: {e}")

        if not stubs:
            log.info("GmeetCollector: 0 Docs in window — nothing to ingest")
            return RunResult(message="no-op (0 docs in window)")

        output_root = ROOT_DIR / self.SPEC.output_subfolder
        already_present: set[str] = set()
        if output_root.exists():
            already_present = {
                p.stem.rsplit("--", 1)[-1]
                for p in output_root.glob("*.md")
                if "--" in p.stem
            }

        files_written: list[Path] = []
        skipped = 0
        highest_created: str | None = state.get("last_seen_ts")
        input_source = "piggyback" if not dry_run and incremental else "cli"

        for stub in stubs:
            file_id = stub.get("id")
            if not file_id:
                log.warning("GmeetCollector: list-row missing id — skipping: %r",
                            sorted(stub.keys()) if isinstance(stub, dict) else type(stub).__name__)
                continue
            short = _short_id(file_id)
            if short in already_present:
                skipped += 1
                continue

            try:
                exported = client.export_doc(file_id)
            except GmeetAPIError as e:
                log.warning("GmeetCollector: export %s — %s", file_id, e)
                continue

            md = _render_markdown(stub, exported, account_id=self._account_id,
                                  input_source=input_source)
            name = stub.get("name") or file_id
            created = stub.get("createdTime") or ""
            date_prefix = str(created)[:10] if created else now_iso()[:10]
            fname = f"{date_prefix}--{_slugify(_meeting_title(name))}--{short}.md"
            target = output_root / fname

            if dry_run:
                log.info("  DRY: would write %s (%d bytes)", target.relative_to(ROOT_DIR), len(md))
                continue

            output_root.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            log.info("  wrote %s", target.relative_to(ROOT_DIR))
            files_written.append(target)

            if created and (highest_created is None or str(created) > str(highest_created)):
                highest_created = str(created)

        if not dry_run and highest_created:
            state["last_seen_ts"] = highest_created
            save_json_state(_STATE_FILE, state)

        return RunResult(
            files_written=tuple(files_written),
            files_skipped=skipped,
            state_keys_touched=("last_seen_ts",) if not dry_run else (),
            message=(
                f"listed {len(stubs)} · wrote {len(files_written)} · "
                f"skipped {skipped} · since={since or '—'}"
            ),
        )
