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

Shape note: one **meeting** → one markdown file (not one Drive Doc → one
file as the original cut shipped). Meet emits up to two Docs per meeting —
a Notes-by-Gemini Doc and a Transcript Doc — that share the same meeting
title minus a locale-dependent kind-suffix. We pair them via a stable
`meeting_key` (sha256 of the normalised stripped title) and merge the
sections into one article. Cross-run safe: a Notes Doc that lands in run N
and a Transcript Doc for the same meeting in run N+1 are merged into the
existing file. Frontmatter shape: `doc_kinds: [...]` + `drive_docs: [...]`
(lists). Legacy singular `doc_kind` / `drive_doc_id` from the pre-pairing
shape is still read on the sibling-scan.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

from adapters.mailbox import MailboxReadError, resolve_reader
from collectors.base import (
    CollectorSpec,
    RunResult,
    Watermark,
    filter_accounts,
    migrate_flat_state,
    register,
    resolve_accounts,
    run_account_loop,
)
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


# ── Output shape ─────────────────────────────────────────────────────

_OUTPUT_SUBFOLDER = "raw/transcripts/gmeet"
_STATE_FILE = STATE_DIR / "gmeet-state.json"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHORT_ID_LEN = 12
_MEETING_KEY_LEN = 12
# Normaliser for the meeting-key hash: lowercase, collapse whitespace, drop
# quote glyphs that vary between Gemini's Notes-Doc and Transcript-Doc renders
# of the same meeting title. Codepoints listed explicitly so we cover ASCII
# straight quotes AND the full curly / angle / low-9 family — IDE auto-replace
# and Gemini's locale handling both swap these silently. Listed by name:
# QUOTATION MARK, APOSTROPHE, LEFT/RIGHT-POINTING DOUBLE ANGLE («»), LEFT/RIGHT
# SINGLE+DOUBLE QUOTATION MARK (‘’ “”), DOUBLE+SINGLE LOW-9 (‚„), HIGH-REVERSED-9
# (‛ ‟), LEFT/RIGHT-POINTING ANGLE (‹›).
_TITLE_NORMALISE_QUOTES_RE = re.compile(
    "[\"'«»"        # " ' « »
    "‘’‚‛"  # ‘ ’ ‚ ‛
    "“”„‟"  # “ ” „ ‟
    "‹›]"             # ‹ ›
)
_TITLE_NORMALISE_WS_RE = re.compile(r"\s+")

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


# Google Docs URLs in a Gemini-notes email body: the doc-id is the path segment
# after `/document/d/`. The id charset is `[A-Za-z0-9_-]`; the trailing
# `/edit?usp=...` or `/view` is ignored by the capture group.
_DOC_URL_RE = re.compile(r"docs\.google\.com/document/d/([A-Za-z0-9_-]+)")


def extract_drive_doc_ids(text: str) -> list[str]:
    """Order-preserving, deduplicated Drive Doc ids found in a text/HTML blob.

    Used by email-discovery to pull the linked Doc out of a
    `gemini-notes@google.com` notification. The doc-url only reliably appears
    in the HTML part of the mail (the plaintext alternative drops it), so
    callers pass `body_html` (falling back to `body_text`).
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _DOC_URL_RE.finditer(text or ""):
        doc_id = m.group(1)
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc_id)
    return out


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


def _meeting_key(name: str) -> str:
    """Stable short hash of the normalised stripped meeting title.

    Two Docs that belong to the same meeting (one Notes, one Transcript) share
    the same `meeting_key` — that's what lets us pair them across runs. The
    normalisation drops whitespace + quote-glyph variation that Gemini
    occasionally introduces between the Notes-Doc and Transcript-Doc renders.
    """
    title = _meeting_title(name).lower()
    title = _TITLE_NORMALISE_QUOTES_RE.sub("", title)
    title = _TITLE_NORMALISE_WS_RE.sub(" ", title).strip()
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:_MEETING_KEY_LEN]


@dataclass
class _Sibling:
    """Existing file in the gmeet output folder, indexed by meeting_key.

    Reads both the new (`doc_kinds: [...]`, `drive_docs: [{...}]`) and the
    legacy singular (`doc_kind:`, `drive_doc_id:`, `drive_doc_name:`) shape so
    a vault populated by the pre-pairing version is still indexed correctly.
    """
    path: Path
    front: dict
    body: str
    doc_kinds: set[str] = field(default_factory=set)
    drive_doc_ids: set[str] = field(default_factory=set)


def _split_frontmatter(text: str) -> tuple[dict, str] | None:
    """Parse a `---\\n…\\n---\\n` frontmatter block; return (data, body) or None.

    Tolerant: returns None if the file has no frontmatter, the frontmatter
    fails to parse, or the data isn't a mapping. Callers should treat None
    as 'not our file, skip'."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, text[end + len("\n---\n"):]


def _scan_siblings(output_root: Path) -> tuple[dict[str, _Sibling], set[str]]:
    """Walk `output_root/*.md`, return (key_map, short_ids_seen).

    `key_map[meeting_key] = _Sibling`: used for pairing — a new Doc whose key
    matches an existing meeting either skips (same kind already present) or
    merges into the existing file.

    `short_ids_seen` is the set of `_short_id(drive_doc_id)` across both the
    filename suffix AND every `drive_docs[*].id` (and legacy `drive_doc_id`)
    in the frontmatter. Used for skip-existing: a merged file's second Doc
    short-id lives only inside frontmatter, not in the filename.
    """
    key_map: dict[str, _Sibling] = {}
    short_ids: set[str] = set()
    if not output_root.exists():
        return key_map, short_ids

    for p in sorted(output_root.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _split_frontmatter(text)
        if parsed is None:
            continue
        front, body = parsed

        # Doc kinds — new shape is list, legacy is singular string.
        kinds: set[str] = set()
        legacy_kind = front.get("doc_kind")
        if isinstance(legacy_kind, str) and legacy_kind:
            kinds.add(legacy_kind)
        for k in front.get("doc_kinds") or []:
            if isinstance(k, str):
                kinds.add(k)

        # Drive doc ids — new shape is `drive_docs: [{id, ...}, ...]`,
        # legacy is singular `drive_doc_id`.
        ids: set[str] = set()
        legacy_id = front.get("drive_doc_id")
        if isinstance(legacy_id, str) and legacy_id:
            ids.add(legacy_id)
        for d in front.get("drive_docs") or []:
            if isinstance(d, dict) and isinstance(d.get("id"), str):
                ids.add(d["id"])
        for did in ids:
            short_ids.add(_short_id(did))

        # Filename short-id (legacy `--<short>.md` skip-existing key).
        if "--" in p.stem:
            short_ids.add(p.stem.rsplit("--", 1)[-1])

        # Meeting key: prefer the original Drive Doc name (carries the
        # locale-dependent suffix that the title field has already stripped);
        # fall back to title (which is the stripped form — same hash anyway).
        name = front.get("drive_doc_name") or front.get("title") or ""
        if isinstance(name, str) and name:
            key = _meeting_key(name)
            # First file wins on collision (alphabetical sort makes it
            # deterministic — earliest dated meeting keeps the slot).
            key_map.setdefault(key, _Sibling(path=p, front=front, body=body,
                                              doc_kinds=kinds, drive_doc_ids=ids))
    return key_map, short_ids




def _app(account_id: str) -> OAuthApp:
    return OAuthApp(
        client_file=google_oauth.resolve_client_file(
            account_id,
            integration_legacy=ROOT_DIR / ".claude" / "gmail-oauth-client.json",
        ),
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
    return google_oauth.bootstrap(_app(account_id), account_id)


# ── Per-account resolution ───────────────────────────────────────────

@dataclass(frozen=True)
class _GmeetAccount:
    """Resolved gmeet config for one `personal.accounts.<id>` entry."""
    account_id: str
    drive_folder_id: str
    drive_folder_name: str
    since: str | None
    max_per_run: int
    # Email-discovery (second discovery source — colleague-shared meetings
    # announced via gemini-notes mails the own-Drive folder-scan never sees).
    email_discovery: bool
    email_senders: tuple[str, ...]
    email_folder: str
    email_backfill_days: int


_DEFAULT_NOTES_SENDER = "gemini-notes@google.com"
_DEFAULT_EMAIL_BACKFILL_DAYS = 30


def _resolve_gmeet_accounts() -> list[_GmeetAccount]:
    """Return the accounts with a `gmeet:` sub-block whose `kind ==
    "gmeet-api"`, via the shared `base.resolve_accounts` kind-dispatch.
    Unknown kinds are silently skipped (graceful-agnostic)."""
    default_max = CONFIG.limits.gmeet_max_per_run

    def _build(aid: str, block: dict) -> _GmeetAccount:
        per_acct_max = block.get("max_per_run")
        ed = block.get("email_discovery")
        if not isinstance(ed, dict):
            ed = {}
        senders = ed.get("senders")
        if not isinstance(senders, (list, tuple)) or not senders:
            senders = (_DEFAULT_NOTES_SENDER,)
        backfill = ed.get("backfill_days")
        return _GmeetAccount(
            account_id=aid,
            drive_folder_id=block.get("drive_folder_id") or "",
            drive_folder_name=block.get("drive_folder_name") or "Meet Recordings",
            since=block.get("since") or None,
            max_per_run=per_acct_max if per_acct_max is not None else default_max,
            email_discovery=bool(ed.get("enabled", True)),
            email_senders=tuple(str(s) for s in senders),
            email_folder=ed.get("folder") or "INBOX",
            email_backfill_days=(
                int(backfill) if backfill is not None else _DEFAULT_EMAIL_BACKFILL_DAYS
            ),
        )

    return resolve_accounts(
        CONFIG.personal.accounts or {}, "gmeet-api", _build, block_key="gmeet"
    )


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

            if expect_json:
                return r.json()
            # Drive's files.export returns charset-less `text/markdown`, which
            # requests decodes as Latin-1 by default → `Ã¤` for `ä`. The bytes
            # are always UTF-8; pin the encoding before reading `.text`.
            r.encoding = "utf-8"
            return r.text

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


# ── Export dead-letter ───────────────────────────────────────────────
# Un-exportable doc-ids (colleague revoked access / doc deleted) were
# re-attempted every run because the 30-day email window re-surfaces the same
# ids (backlog gmeet-export-dead-letter.md; audit 2026-08-25: one id 404ing
# across runs). Negative cache per account in gmeet-state.json under
# `export_failed`; bounded re-probe so a re-granted doc eventually imports.


def _record_export_failure(dead: dict, file_id: str, error: str, *, now: str) -> None:
    entry = dead.setdefault(file_id, {"first_seen": now, "attempts": 0})
    entry["attempts"] = entry.get("attempts", 0) + 1
    entry["last_error"] = str(error)[:200]
    entry["last_attempt"] = now


def _dead_letter_skip(
    entry: dict | None, *, now: str, max_attempts: int, reprobe_days: int
) -> bool:
    """True while the id is over its attempt budget AND inside the re-probe
    window; after the window one retry is allowed so a re-granted doc
    eventually imports. Unparseable timestamps skip (fail-closed: no
    re-attempt storm on corrupt state)."""
    if not entry or entry.get("attempts", 0) < max_attempts:
        return False
    last = entry.get("last_attempt", "")
    if not last:
        return True
    try:
        cutoff = datetime.fromisoformat(last) + timedelta(days=reprobe_days)
        return datetime.fromisoformat(now) < cutoff
    except ValueError:
        return True


# ── Rendering ────────────────────────────────────────────────────────

_HEADING_BY_KIND = {
    "transcript": "## Transcript",
    "notes": "## Summary",
    "unknown": "## Notes",
}

# Section markers: a body section starts with a heading line that begins with
# `## ` AND matches one of the kind-headings above (case-insensitive). The
# merge path uses this to detect "this section is already present" so we don't
# double-append the same Doc's content on re-runs.
_SECTION_HEADINGS = {v.lower() for v in _HEADING_BY_KIND.values()}


def _section_body(kind: str, exported: str) -> str:
    """Render one kind's content as a `## Heading\\n\\n<body>` block."""
    heading = _HEADING_BY_KIND.get(kind, "## Notes")
    return f"{heading}\n\n{exported.strip()}\n"


def _render_markdown(docs: list[tuple[dict, str]], *, account_id: str, input_source: str) -> str:
    """Render one markdown file from one or more (Doc, exported-markdown) pairs.

    All Docs in the list belong to the same meeting (same `meeting_key`); they
    are typically (Notes-Doc, Transcript-Doc) but the function handles N≥1.
    Section order follows the input order: callers pass Notes before Transcript
    when both are present so the summary leads the article.
    """
    if not docs:
        raise ValueError("_render_markdown: need at least one Doc")

    # Frontmatter — drive from the FIRST Doc's metadata (canonical title /
    # started_at), augment with the per-Doc list under `drive_docs`.
    first_doc, _ = docs[0]
    first_name = first_doc.get("name") or first_doc.get("id") or "unknown"
    title = _meeting_title(first_name)
    created = first_doc.get("createdTime")

    drive_docs_entries: list[dict[str, Any]] = []
    kinds_in_order: list[str] = []
    for doc, _exported in docs:
        file_id = doc.get("id") or "unknown"
        name = doc.get("name") or file_id
        kind = _classify_doc(name)
        if kind not in kinds_in_order:
            kinds_in_order.append(kind)
        drive_docs_entries.append({
            "id": file_id,
            "name": name,
            "kind": kind,
            "url": doc.get("webViewLink"),
            "created": doc.get("createdTime"),
        })

    front: dict[str, Any] = {
        "type": "transcript",
        "source": "gmeet",
        "meeting_id": _meeting_key(first_name),
        "title": title,
        "doc_kinds": kinds_in_order,
        "started_at": created,
        "drive_docs": drive_docs_entries,
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
    header_bits.append("+".join(kinds_in_order))

    sections = [_section_body(_classify_doc(doc.get("name") or doc.get("id") or ""),
                              exported) for doc, exported in docs]

    parts: list[str] = [
        f"---\n{fm}\n---",
        "",
        f"# {title}",
        "",
        f"_{' · '.join(header_bits)}_",
        "",
        "\n".join(sections).rstrip(),
        "",
    ]
    return "\n".join(parts) + "\n"


def _merge_into_sibling(sibling: _Sibling, doc: dict, exported: str,
                        *, account_id: str, input_source: str) -> str:
    """Append a new Doc's section into an existing meeting file. Returns the
    new full text (caller writes it back). Updates `doc_kinds` + `drive_docs`
    in the frontmatter and migrates legacy singular fields to the list shape
    in the same pass."""
    new_kind = _classify_doc(doc.get("name") or doc.get("id") or "")

    front = dict(sibling.front)  # shallow copy — we mutate it
    file_id = doc.get("id") or "unknown"
    name = doc.get("name") or file_id

    # ── doc_kinds: list (migrate legacy singular `doc_kind` if present) ──
    kinds: list[str] = []
    legacy = front.pop("doc_kind", None)
    if isinstance(legacy, str) and legacy:
        kinds.append(legacy)
    for k in front.get("doc_kinds") or []:
        if isinstance(k, str) and k not in kinds:
            kinds.append(k)
    if new_kind not in kinds:
        kinds.append(new_kind)
    front["doc_kinds"] = kinds

    # ── drive_docs: list of {id, name, kind, url, created} ──────────────
    drive_docs: list[dict[str, Any]] = []
    legacy_id = front.pop("drive_doc_id", None)
    legacy_name = front.pop("drive_doc_name", None)
    legacy_url = front.pop("drive_url", None)
    if isinstance(legacy_id, str) and legacy_id:
        # Re-classify legacy entry from its name so the doc_kinds list above
        # stays consistent with drive_docs.
        legacy_kind = _classify_doc(legacy_name or "") if isinstance(legacy_name, str) else "unknown"
        drive_docs.append({
            "id": legacy_id,
            "name": legacy_name if isinstance(legacy_name, str) else legacy_id,
            "kind": legacy_kind,
            "url": legacy_url if isinstance(legacy_url, str) else None,
            "created": front.get("started_at"),
        })
    for d in front.get("drive_docs") or []:
        if isinstance(d, dict) and d.get("id") and d["id"] not in {x["id"] for x in drive_docs}:
            drive_docs.append(d)
    drive_docs.append({
        "id": file_id,
        "name": name,
        "kind": new_kind,
        "url": doc.get("webViewLink"),
        "created": doc.get("createdTime"),
    })
    # Drop None values per drive_docs entry to keep frontmatter terse.
    front["drive_docs"] = [{k: v for k, v in d.items() if v is not None} for d in drive_docs]

    # ── Provenance refresh ────────────────────────────────────────────────
    front["ingested_at"] = now_iso()
    front["input_source"] = input_source
    front["account_id"] = account_id

    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()
    body = sibling.body.rstrip() + "\n\n" + _section_body(new_kind, exported)
    return f"---\n{fm}\n---\n{body.rstrip()}\n"


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
            google_oauth.token_path(_app(a.account_id), a.account_id).exists()
            for a in self._accounts
        )

    def run(
        self, *, dry_run: bool = False, incremental: bool = False, account: str | None = None
    ) -> RunResult:
        if not self._accounts:
            log.info("GmeetCollector: no accounts with kind=gmeet-api — skipping.")
            return RunResult(message="no-op (no gmeet accounts configured)")

        accounts = filter_accounts(self._accounts, account)
        if not accounts:
            return RunResult(message=f"no-op (no gmeet account {account!r} configured)")

        # Output dir + sibling-map are shared across accounts (Drive file ids
        # are globally unique, the flat output folder is fine). The sibling
        # map indexes existing meeting files by their `meeting_key` so a new
        # Doc whose key matches can be paired (merged) instead of written as a
        # second file. `already_present` is the union of filename short-ids
        # AND frontmatter `drive_docs[*].id` short-ids — a merged file's second
        # Doc id lives only inside frontmatter.
        output_root = ROOT_DIR / self.SPEC.output_subfolder
        sibling_map, already_present = _scan_siblings(output_root)

        state = load_json_state(_STATE_FILE)
        # Migrate the pre-multi-tenant flat shape into state["default"] so a
        # clean lift doesn't lose the watermark (shared with jamie, verbatim).
        migrate_flat_state(state, "last_seen_ts", log=log, name="GmeetCollector")

        scan = functools.partial(
            self._run_one_account,
            state=state,
            already_present=already_present,
            sibling_map=sibling_map,
            dry_run=dry_run,
            incremental=incremental,
        )
        outcome = run_account_loop(accounts, scan, log=log, name="GmeetCollector")

        if not dry_run and outcome.any_state_touched:
            save_json_state(_STATE_FILE, state)

        all_files = [f for files, _skipped in outcome.payloads for f in files]
        total_skipped = sum(skipped for _files, skipped in outcome.payloads)
        return RunResult(
            files_written=tuple(all_files),
            files_skipped=total_skipped,
            state_keys_touched=(
                tuple(a.account_id for a in accounts) if outcome.any_state_touched else ()
            ),
            message=" · ".join(outcome.messages) or "no-op",
        )

    def _run_one_account(
        self,
        acct: _GmeetAccount,
        *,
        state: dict,
        already_present: set[str],
        sibling_map: dict[str, _Sibling],
        dry_run: bool,
        incremental: bool,
    ) -> tuple[str, tuple[list[Path], int], bool]:
        """Run one account's scan. Returns (message, (files, skipped), state_touched)
        for the harness's payload-generic aggregation. Mutates
        `state[acct.account_id]['last_seen_ts']` only on a successful scan that
        advanced the watermark — failures leave it untouched (hold-on-failure)."""
        sess, err = google_oauth.session(_app(acct.account_id), acct.account_id)
        if err:
            return f"auth: {err}", ([], 0), False

        client = _DriveClient(session=sess, timeout_s=self._timeout_s)

        per_acct_state = state.get(acct.account_id) or {}

        # ── Discovery source 1: own-Drive "Meet Recordings" folder scan ──
        # Meetings the operator's own account recorded. A folder problem must
        # NOT abort the account — email-discovery below is an independent source.
        folder_stubs: list[dict] = []
        folder_note = ""
        folder_id = acct.drive_folder_id
        if not folder_id:
            folder_id = client.resolve_folder_id(acct.drive_folder_name)
            if folder_id:
                # Drive folder-name search is name-collision-prone (Workspace
                # users sometimes have multiple "Meet Recordings" — personal +
                # shared-drive). Surface the resolved id once per run so the
                # operator can pin it in config and stop trusting the search.
                log.warning(
                    "GmeetCollector[%s]: drive_folder_id is empty — auto-resolved by "
                    "name to %s. Pin it in config (personal.accounts.%s.gmeet.drive_folder_id) "
                    "for collision-safe runs.",
                    acct.account_id, folder_id, acct.account_id,
                )
        if folder_id:
            since = per_acct_state.get("last_seen_ts") if incremental else acct.since
            log.info(
                "GmeetCollector[%s]: listing Docs (folder=%s, since=%s, limit=%d)",
                acct.account_id, folder_id, since or "—", acct.max_per_run,
            )
            try:
                folder_stubs = list(client.list_docs(folder_id, since=since, limit=acct.max_per_run))
            except GmeetAPIError as e:
                log.error("GmeetCollector[%s]: folder list failed: %s", acct.account_id, e)
                folder_note = f"folder-list failed: {e}"
        else:
            folder_note = (
                f"folder {acct.drive_folder_name!r} not found "
                f"(set personal.accounts.{acct.account_id}.gmeet.drive_folder_id)"
            )

        # ── Discovery source 2: gemini-notes email links ──
        # Meetings a colleague recorded + auto-shared org-wide; these never land
        # in the operator's own Drive folder, but the notification email carries
        # the (org-readable) Drive doc-id. Reuses the account's configured
        # mailbox reader; windowed scan + Drive-file-id dedup is idempotent
        # without a separate email watermark.
        email_stubs, email_note = self._discover_via_email(acct, client, already_present)

        # Union by Drive file-id (a doc seen by both sources ingests once).
        folder_ids = {s.get("id") for s in folder_stubs if s.get("id")}
        stubs: list[dict] = list(folder_stubs)
        for s in email_stubs:
            if s.get("id") and s["id"] not in folder_ids:
                stubs.append(s)

        notes = " · ".join(n for n in (folder_note, email_note) if n)
        if not stubs:
            return f"no-op{(' · ' + notes) if notes else ''}", ([], 0), False

        # Group the listed Docs by `meeting_key`. Notes-Doc + Transcript-Doc
        # for the same meeting share a key and ingest as one file (combined or
        # merged into an existing one). Order within a group: Notes first if
        # present (summary leads), then Transcript, then unknown.
        groups: dict[str, list[dict]] = {}
        for stub in stubs:
            file_id = stub.get("id")
            if not file_id:
                log.warning(
                    "GmeetCollector[%s]: list-row missing id — skipping: %r",
                    acct.account_id,
                    sorted(stub.keys()) if isinstance(stub, dict) else type(stub).__name__,
                )
                continue
            name = stub.get("name") or file_id
            groups.setdefault(_meeting_key(name), []).append(stub)
        _KIND_ORDER = {"notes": 0, "transcript": 1, "unknown": 2}
        for key in groups:
            groups[key].sort(key=lambda d: _KIND_ORDER.get(
                _classify_doc(d.get("name") or ""), 99))

        files_written: list[Path] = []
        skipped = 0
        watermark = Watermark.seed(per_acct_state.get("last_seen_ts"))
        dead: dict = per_acct_state.get("export_failed") or {}
        dead_touched = False
        skipped_dead = 0
        input_source = "piggyback" if not dry_run and incremental else "cli"

        for key, doc_stubs in groups.items():
            sibling = sibling_map.get(key)

            # Filter out stubs already represented in an existing file (by
            # filename short-id or by frontmatter drive_docs id) AND already
            # carrying their kind in the sibling. The remaining stubs need to
            # be exported + merged or written fresh.
            new_stubs: list[dict] = []
            for stub in doc_stubs:
                file_id = stub.get("id") or ""
                short = _short_id(file_id)
                if short in already_present:
                    skipped += 1
                    continue
                if sibling is not None:
                    new_kind = _classify_doc(stub.get("name") or file_id)
                    if new_kind in sibling.doc_kinds:
                        # Same meeting, same kind, different Drive Doc id —
                        # rare (Gemini occasionally regenerates a Doc). Skip
                        # to avoid double-appending; the operator can delete
                        # the file manually if they want the regen.
                        log.info(
                            "GmeetCollector[%s]: %s — same kind (%s) already present in %s, skipping",
                            acct.account_id, file_id, new_kind, sibling.path.name,
                        )
                        skipped += 1
                        continue
                new_stubs.append(stub)

            if not new_stubs:
                continue

            # Export every new stub before we decide write-vs-merge so a
            # mid-group export failure doesn't write a half-merged file.
            exports: list[tuple[dict, str]] = []
            for stub in new_stubs:
                file_id = stub.get("id") or ""
                if _dead_letter_skip(
                    dead.get(file_id),
                    now=now_iso(),
                    max_attempts=CONFIG.limits.gmeet_export_dead_letter_attempts,
                    reprobe_days=CONFIG.limits.gmeet_export_dead_letter_reprobe_days,
                ):
                    skipped_dead += 1
                    continue
                try:
                    exported = client.export_doc(file_id)
                except GmeetAPIError as e:
                    log.warning("GmeetCollector[%s]: export %s — %s",
                                acct.account_id, file_id, e)
                    _record_export_failure(dead, file_id, str(e), now=now_iso())
                    dead_touched = True
                    continue
                if dead.pop(file_id, None) is not None:
                    dead_touched = True
                exports.append((stub, exported))

            if not exports:
                continue

            if sibling is not None:
                # Merge each new Doc's section into the existing meeting file.
                text = sibling.body  # base body; _merge_into_sibling layers on
                current = sibling
                target = sibling.path
                for stub, exported in exports:
                    text = _merge_into_sibling(
                        current, stub, exported,
                        account_id=acct.account_id, input_source=input_source,
                    )
                    if dry_run:
                        log.info("  DRY[%s]: would merge %s into %s (%d bytes)",
                                 acct.account_id, stub.get("id") or "?",
                                 target.relative_to(ROOT_DIR), len(text))
                        continue
                    # Re-parse the merged text so the next iteration of the
                    # group (rare: three Docs in one meeting) sees the latest
                    # frontmatter + body, not the original sibling's.
                    parsed = _split_frontmatter(text)
                    if parsed is None:
                        log.error(
                            "GmeetCollector[%s]: post-merge frontmatter unparseable for %s — aborting group",
                            acct.account_id, target.relative_to(ROOT_DIR),
                        )
                        break
                    new_front, new_body = parsed
                    current = _Sibling(
                        path=target, front=new_front, body=new_body,
                        doc_kinds=set(new_front.get("doc_kinds") or []),
                        drive_doc_ids={d.get("id") for d in (new_front.get("drive_docs") or []) if isinstance(d, dict) and d.get("id")},
                    )
                    target.write_text(text, encoding="utf-8")
                    # Only own-folder docs advance the folder watermark; email-
                    # discovered docs are deduped by file-id, not by createdTime.
                    if stub.get("id") in folder_ids:
                        watermark.observe(stub.get("createdTime"))
                    short = _short_id(stub.get("id") or "")
                    if short:
                        already_present.add(short)
                if not dry_run:
                    log.info("  [%s] merged %d Doc(s) into %s",
                             acct.account_id, len(exports), target.relative_to(ROOT_DIR))
                    # Keep sibling_map in sync for cross-account reuse later
                    # in the same run.
                    sibling_map[key] = current
                    files_written.append(target)
                continue

            # No sibling — write a fresh combined file for this meeting.
            md = _render_markdown(exports, account_id=acct.account_id,
                                  input_source=input_source)
            first_doc, _ = exports[0]
            first_name = first_doc.get("name") or first_doc.get("id") or "unknown"
            first_created = first_doc.get("createdTime") or ""
            date_prefix = str(first_created)[:10] if first_created else now_iso()[:10]
            # Filename: meeting-key suffix (was: short-Doc-id). Stable across
            # Doc-of-different-kind appends — the file never gets renamed when
            # a paired Doc arrives later.
            fname = f"{date_prefix}--{_slugify(_meeting_title(first_name))}--{key}.md"
            target = (ROOT_DIR / self.SPEC.output_subfolder) / fname

            if dry_run:
                log.info("  DRY[%s]: would write %s (%d Doc(s), %d bytes)",
                         acct.account_id, target.relative_to(ROOT_DIR), len(exports), len(md))
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            log.info("  [%s] wrote %s (%d Doc(s))",
                     acct.account_id, target.relative_to(ROOT_DIR), len(exports))
            files_written.append(target)

            # Mirror a one-liner into daily/<date>/meetings.md.
            try:
                from core import daily_capture as _daily_capture
                if re.match(r"^\d{4}-\d{2}-\d{2}$", date_prefix):
                    rollup_line = f"- **gmeet** · {_meeting_title(first_name)} → [[{target.stem}]]"
                    _daily_capture.append(date_prefix, "meetings", rollup_line)
            except Exception:  # noqa: BLE001
                log.exception("daily-rollup append failed for gmeet meeting %s", key)

            # Register the newly-written file in the sibling_map so a later
            # group in this same run (or a later account in the multi-tenant
            # loop) merges into it instead of writing a duplicate.
            parsed = _split_frontmatter(md)
            if parsed is not None:
                new_front, new_body = parsed
                sibling_map[key] = _Sibling(
                    path=target, front=new_front, body=new_body,
                    doc_kinds=set(new_front.get("doc_kinds") or []),
                    drive_doc_ids={d.get("id") for d in (new_front.get("drive_docs") or []) if isinstance(d, dict) and d.get("id")},
                )
            already_present.add(key)
            for stub, _exported in exports:
                short = _short_id(stub.get("id") or "")
                if short:
                    already_present.add(short)
                # Only own-folder docs advance the folder watermark; email-
                # discovered docs are deduped by file-id, not by createdTime.
                if stub.get("id") in folder_ids:
                    watermark.observe(stub.get("createdTime"))

        state_touched = False
        if not dry_run and (watermark.advanced or dead_touched):
            if watermark.advanced:
                per_acct_state["last_seen_ts"] = watermark.value
            if dead:
                per_acct_state["export_failed"] = dead
            else:
                per_acct_state.pop("export_failed", None)
            state[acct.account_id] = per_acct_state
            state_touched = True

        if skipped_dead:
            log.info(
                "GmeetCollector[%s]: %d un-exportable doc(s) parked in dead-letter "
                "(re-probe after %dd)",
                acct.account_id, skipped_dead,
                CONFIG.limits.gmeet_export_dead_letter_reprobe_days,
            )

        summary = f"wrote {len(files_written)} · skipped {skipped}"
        if skipped_dead:
            summary += f" · {skipped_dead} dead-letter"
        return (
            f"{notes} · {summary}" if notes else f"listed {len(stubs)} · {summary}",
            (files_written, skipped),
            state_touched,
        )

    def _discover_via_email(
        self,
        acct: _GmeetAccount,
        client: _DriveClient,
        already_present: set[str],
    ) -> tuple[list[dict], str]:
        """Find Drive Doc-ids announced in gemini-notes emails for this account.

        Reuses the account's configured mailbox reader (`resolve_reader`), scans
        a bounded recent window of `email_folder`, keeps messages from
        `email_senders`, and pulls `docs.google.com/document/d/<id>` out of the
        message body (HTML part preferred — the plaintext alternative drops the
        link). Returns Drive `files.get` metadata stubs for ids not already
        ingested, plus a one-line note. Any reader / permission failure degrades
        to `([], note)` so the folder-scan results still ship.
        """
        if not acct.email_discovery:
            return [], ""
        account_body = (CONFIG.personal.accounts or {}).get(acct.account_id)
        if not isinstance(account_body, dict):
            return [], "email: no account body"
        body = dict(account_body)
        body.setdefault("account_id", acct.account_id)
        try:
            reader = resolve_reader(body)
        except Exception as e:  # noqa: BLE001
            log.warning("GmeetCollector[%s]: email reader resolve failed: %s", acct.account_id, e)
            return [], "email: reader-resolve error"
        if reader is None:
            return [], "email: no reader configured"

        since = datetime.now(timezone.utc) - timedelta(days=acct.email_backfill_days)
        senders = tuple(s.lower() for s in acct.email_senders)
        doc_ids: list[str] = []
        seen: set[str] = set()
        try:
            for msg in reader.scan_deep(folder=acct.email_folder, since=since):
                frm = (msg.meta.from_addr or "").lower()
                if not any(s in frm for s in senders):
                    continue
                blob = f"{msg.body_html or ''}\n{msg.body_text or ''}"
                for did in extract_drive_doc_ids(blob):
                    if did not in seen:
                        seen.add(did)
                        doc_ids.append(did)
        except MailboxReadError as e:
            log.warning("GmeetCollector[%s]: email scan failed: %s", acct.account_id, e)
            return [], f"email-scan failed: {e}"
        except Exception as e:  # noqa: BLE001
            log.exception("GmeetCollector[%s]: email scan crashed", acct.account_id)
            return [], f"email-scan error: {type(e).__name__}"

        # Skip ids already ingested (filename short-id / frontmatter) before
        # spending a files.get — the same dedup key the write loop uses.
        new_ids = [d for d in doc_ids if _short_id(d) not in already_present]
        stubs: list[dict] = []
        for did in new_ids:
            try:
                meta = client._get(
                    f"{_DRIVE_BASE}/files/{did}",
                    params={"fields": "id,name,createdTime,modifiedTime,webViewLink"},
                )
            except GmeetAPIError as e:
                log.warning("GmeetCollector[%s]: files.get %s failed: %s", acct.account_id, did, e)
                continue
            if isinstance(meta, dict) and meta.get("id"):
                stubs.append(meta)
        return stubs, f"email: {len(doc_ids)} linked / {len(stubs)} new"
