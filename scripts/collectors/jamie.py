"""Jamie Collector — pulls meetings from the Jamie AI public API.

Substrate-shaped: configured via `CONFIG.personal.jamie` (single-tenant
flat block, not the multi-account `personal.accounts` shape). The API
key lives in an environment variable; only the variable *name* sits in
config.yaml. Missing/empty env var → `is_configured()` returns False
and the collector is silently skipped (graceful-agnostic).

Network shape:
- Base URL + auth header set as module constants. Bearer jk_... per the
  Jamie API docs; if first-request discovery reveals a different shape,
  flip `_AUTH_HEADER` / `_BASE_URL` and re-run. The first response
  triggers a one-shot DEBUG log so the operator can verify.
- httpx is already a transitive dependency (used by ollama_client + others).
- No connection pooling — a JamieCollector run does N+1 requests
  (one list + one get-per-meeting), then exits.

State:
- `state/jamie-state.json` carries `last_seen_ts` (ISO 8601). Incremental
  runs query `/meetings?since=<last_seen_ts>`; the highest `started_at`
  seen during a successful run becomes the new `last_seen_ts`.
- Skip-existing is keyed on meeting_id: any file under
  `raw/transcripts/jamie/` whose name ends in `--<short-id>.md` is
  considered already ingested.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx
import yaml

from collectors.base import Collector, CollectorSpec, RunResult, register
from core.config import RAW_DIR, ROOT_DIR, STATE_DIR, now_iso
from core.wiki_config import CONFIG

log = logging.getLogger(__name__)


# ── API constants (verify on first live request) ─────────────────────

_BASE_URL = "https://api.meetjamie.ai/v1"
_AUTH_HEADER = "Authorization"      # value: f"Bearer {api_key}"
_USER_AGENT = "llm-wiki/jamie-collector"

# Per `JAMIE_KEY_TYPE` — selects route prefix.
_ROUTE_PERSONAL = "me"
_ROUTE_WORKSPACE = "workspace"

# Query parameter names. Adjust if the live API uses different keys.
_PARAM_SINCE = "since"              # ISO 8601 — filter by started_at >= since
_PARAM_LIMIT = "limit"
_PARAM_CURSOR = "cursor"            # opaque pagination cursor (if applicable)

_STATE_FILE = STATE_DIR / "jamie-state.json"
_API_VERSION = "v1"


# ── Output shape ─────────────────────────────────────────────────────

_OUTPUT_SUBFOLDER = "raw/transcripts/jamie"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DEFAULT_SHORT_ID_LEN = 8


def _slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _short_id(meeting_id: str) -> str:
    """Take the leading 8 hex chars of the UUID portion of a Jamie meeting id.

    Jamie ids look like `m_<uuid>` or pure UUIDs — we just strip any prefix
    up to the first hex run and take the first 8 chars. Idempotent on input
    that's already short.
    """
    hex_match = re.search(r"[a-f0-9]{8}", meeting_id.lower())
    return hex_match.group(0) if hex_match else meeting_id[:_DEFAULT_SHORT_ID_LEN]


# ── HTTP client (inline — no adapter family yet) ─────────────────────

class JamieAPIError(RuntimeError):
    """Raised on non-recoverable Jamie API failures (401, persistent 5xx, schema)."""


@dataclass
class _JamieClient:
    api_key: str
    key_type: str               # "personal" | "workspace"
    timeout_s: float
    _logged_discovery: bool = False

    @property
    def route_prefix(self) -> str:
        return _ROUTE_PERSONAL if self.key_type == "personal" else _ROUTE_WORKSPACE

    @property
    def headers(self) -> dict[str, str]:
        return {
            _AUTH_HEADER: f"Bearer {self.api_key}",
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """One GET with single retry on 429/5xx. Returns parsed JSON or raises."""
        url = f"{_BASE_URL}/{self.route_prefix}{path}"
        for attempt in (1, 2):
            try:
                r = httpx.get(url, params=params or {}, headers=self.headers, timeout=self.timeout_s)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise JamieAPIError(f"network failure on {path}: {type(e).__name__}: {e}") from e
                log.warning("jamie %s: %s — retrying once in 5s", path, type(e).__name__)
                time.sleep(5)
                continue

            if r.status_code == 401:
                raise JamieAPIError(
                    f"401 on {path} — api key invalid or revoked. Check env var content."
                )
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                if attempt == 2:
                    raise JamieAPIError(f"429 on {path} after retry (waited {wait}s)")
                log.warning("jamie %s: 429 rate-limit — sleeping %ds before retry", path, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                if attempt == 2:
                    raise JamieAPIError(f"persistent {r.status_code} on {path}: {r.text[:200]}")
                log.warning("jamie %s: %d — retrying once in 5s", path, r.status_code)
                time.sleep(5)
                continue
            if r.status_code != 200:
                raise JamieAPIError(f"unexpected {r.status_code} on {path}: {r.text[:200]}")

            payload = r.json()
            if not self._logged_discovery:
                log.debug("jamie discovery: GET %s keys=%s", path, _shallow_keys(payload))
                self._logged_discovery = True
            return payload

        raise JamieAPIError(f"unreachable: exhausted retries on {path}")

    def list_meetings(
        self, *, since: str | None = None, limit: int | None = None,
    ) -> Iterator[dict]:
        """Yield meeting summaries. Paginates if the response carries a cursor.

        Best-effort against a doc-only-partially-public API: accepts the most
        common pagination shapes (`items` + `next_cursor`, or bare list).
        """
        params: dict[str, Any] = {}
        if since:
            params[_PARAM_SINCE] = since
        if limit:
            params[_PARAM_LIMIT] = limit

        seen = 0
        cursor: str | None = None
        while True:
            page_params = dict(params)
            if cursor:
                page_params[_PARAM_CURSOR] = cursor
            payload = self._get("/meetings", page_params)

            items, next_cursor = _normalize_list_payload(payload)
            for item in items:
                yield item
                seen += 1
                if limit and seen >= limit:
                    return
            if not next_cursor:
                return
            cursor = next_cursor

    def get_meeting(self, meeting_id: str) -> dict:
        """Full meeting payload (summary + transcript + participants + tasks)."""
        return self._get(f"/meetings/{meeting_id}")


def _shallow_keys(payload: Any) -> str:
    """Stringify the top-level shape of a payload for one-shot discovery log."""
    if isinstance(payload, dict):
        return f"dict({sorted(payload.keys())})"
    if isinstance(payload, list):
        return f"list(len={len(payload)})"
    return type(payload).__name__


def _normalize_list_payload(payload: Any) -> tuple[list[dict], str | None]:
    """Accept either {items:[...], next_cursor: "..."} or a bare list."""
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, dict):
        raise JamieAPIError(f"unexpected list response shape: {type(payload).__name__}")
    items = payload.get("items") or payload.get("data") or payload.get("meetings") or []
    if not isinstance(items, list):
        raise JamieAPIError(f"list payload had no list under items/data/meetings: keys={sorted(payload.keys())}")
    cursor = payload.get("next_cursor") or payload.get("nextCursor") or payload.get("cursor")
    return items, (cursor if isinstance(cursor, str) and cursor else None)


# ── Rendering ────────────────────────────────────────────────────────

def _participants_label(participants: list[dict]) -> str:
    """Inline label for the header line."""
    names = [p.get("name") or p.get("email") or "?" for p in participants if isinstance(p, dict)]
    if not names:
        return "—"
    if len(names) <= 3:
        return ", ".join(names)
    return f"{', '.join(names[:3])} +{len(names) - 3}"


def _duration_minutes(meeting: dict) -> int | None:
    """Best-effort minute extraction from any of the shapes the API might use."""
    if "duration_min" in meeting:
        return int(meeting["duration_min"])
    if "duration_s" in meeting:
        return int(meeting["duration_s"]) // 60
    if "duration" in meeting:
        try:
            return int(meeting["duration"]) // 60
        except (TypeError, ValueError):
            return None
    return None


def _render_markdown(meeting: dict, *, account_id: str, key_type: str, input_source: str) -> str:
    """One markdown file per meeting. Sections only emitted when source data present."""
    meeting_id = meeting.get("id") or meeting.get("meeting_id") or "unknown"
    title = meeting.get("title") or meeting.get("name") or meeting_id
    started_at = meeting.get("started_at") or meeting.get("startedAt") or meeting.get("start_time")
    ended_at = meeting.get("ended_at") or meeting.get("endedAt") or meeting.get("end_time")
    duration_min = _duration_minutes(meeting)
    participants = meeting.get("participants") or meeting.get("attendees") or []
    tags = meeting.get("tags") or []
    summary = (meeting.get("summary") or meeting.get("summary_markdown") or "").strip()
    action_items = meeting.get("action_items") or meeting.get("tasks") or []
    transcript_segments = meeting.get("transcript") or meeting.get("segments") or []
    jamie_url = meeting.get("url") or meeting.get("share_url")
    calendar_event = meeting.get("calendar_event_id") or meeting.get("event_id")

    front: dict[str, Any] = {
        "type": "transcript",
        "source": "jamie",
        "meeting_id": meeting_id,
        "title": title,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_min": duration_min,
        "participants": [
            {"name": p.get("name"), "email": p.get("email")}
            for p in participants if isinstance(p, dict)
        ],
        "calendar_event": calendar_event,
        "tags": list(dict.fromkeys(["jamie", "meeting", *[str(t) for t in tags if t]])),
        "ingested_at": now_iso(),
        "input_source": input_source,
        "account_id": account_id,
        "key_type": key_type,
        "api_version": _API_VERSION,
        "jamie_url": jamie_url,
        "transcript_status": "pending" if not transcript_segments and not summary else None,
    }
    # Drop empty keys for a clean frontmatter.
    front = {k: v for k, v in front.items() if v not in (None, [], "")}

    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    parts: list[str] = [f"---\n{fm}\n---", "", f"# {title}", ""]
    header_bits = []
    if duration_min is not None:
        header_bits.append(f"{duration_min} min")
    header_bits.append(_participants_label(participants))
    if started_at:
        header_bits.append(str(started_at)[:10])
    parts.append(f"_{' · '.join(header_bits)}_")
    parts.append("")

    if summary:
        parts.append("## Summary")
        parts.append("")
        parts.append(summary)
        parts.append("")

    if action_items:
        parts.append("## Action items")
        parts.append("")
        for item in action_items:
            if not isinstance(item, dict):
                continue
            owner = item.get("owner") or item.get("assignee") or item.get("name") or ""
            task = item.get("task") or item.get("text") or item.get("description") or ""
            if not task:
                continue
            prefix = f"{owner}: " if owner else ""
            parts.append(f"- [ ] {prefix}{task}")
        parts.append("")

    if transcript_segments:
        parts.append("## Transcript")
        parts.append("")
        for seg in transcript_segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker") or seg.get("speaker_name") or "unknown"
            text = (seg.get("text") or "").strip()
            start_s = seg.get("start_s") or seg.get("start") or 0
            try:
                ts = int(float(start_s))
            except (TypeError, ValueError):
                ts = 0
            anchor = f"[{ts // 60:02d}:{ts % 60:02d}]"
            if text:
                parts.append(f"**{speaker}** {anchor} — {text}")
        parts.append("")

    return "\n".join(parts) + "\n"


# ── State persistence ────────────────────────────────────────────────

def _load_state() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Collector ────────────────────────────────────────────────────────

@register
class JamieCollector:
    SPEC = CollectorSpec(
        name="jamie",
        output_subfolder=_OUTPUT_SUBFOLDER,
        piggyback_default=True,
        piggyback_cooldown_hours=6,
        supports_incremental=True,
        supports_account_loop=False,
    )

    def __init__(self) -> None:
        jamie_cfg = CONFIG.personal.jamie
        self._api_key_env = jamie_cfg.api_key_env or ""
        self._key_type = jamie_cfg.key_type or "personal"
        self._configured_since = jamie_cfg.since or None
        self._account_id = jamie_cfg.account_id or "default"
        self._max_per_run = (
            jamie_cfg.max_per_run
            if jamie_cfg.max_per_run is not None
            else CONFIG.limits.jamie_max_per_run
        )
        self._timeout_s = float(CONFIG.limits.jamie_request_timeout_s)
        self._api_key = os.environ.get(self._api_key_env, "").strip() if self._api_key_env else ""

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self.is_configured():
            log.info("JamieCollector: api_key_env=%r not set in environment — skipping.",
                     self._api_key_env)
            return RunResult(message="no-op (jamie api key env var unset)")

        output_root = ROOT_DIR / self.SPEC.output_subfolder
        state = _load_state()
        since = state.get("last_seen_ts") if incremental else self._configured_since

        client = _JamieClient(
            api_key=self._api_key, key_type=self._key_type, timeout_s=self._timeout_s,
        )

        log.info(
            "JamieCollector: listing meetings (key_type=%s, since=%s, limit=%d)",
            self._key_type, since or "—", self._max_per_run,
        )

        try:
            summaries = list(client.list_meetings(since=since, limit=self._max_per_run))
        except JamieAPIError as e:
            log.error("JamieCollector: list failed: %s", e)
            return RunResult(message=f"list failed: {e}")

        if not summaries:
            log.info("JamieCollector: 0 meetings in window — nothing to ingest")
            return RunResult(message="no-op (0 meetings in window)")

        already_present: set[str] = set()
        if output_root.exists():
            already_present = {
                p.stem.rsplit("--", 1)[-1]
                for p in output_root.glob("*.md")
                if "--" in p.stem
            }

        files_written: list[Path] = []
        skipped = 0
        highest_started: str | None = state.get("last_seen_ts")

        input_source = "piggyback" if not dry_run and incremental else "cli"

        for summary in summaries:
            mid = summary.get("id") or summary.get("meeting_id")
            if not mid:
                log.warning("JamieCollector: list-row missing id — skipping: %r",
                            sorted(summary.keys()) if isinstance(summary, dict) else type(summary).__name__)
                continue
            short = _short_id(mid)
            if short in already_present:
                skipped += 1
                continue

            try:
                full = client.get_meeting(mid)
            except JamieAPIError as e:
                log.warning("JamieCollector: %s — %s", mid, e)
                continue

            md = _render_markdown(full, account_id=self._account_id,
                                  key_type=self._key_type, input_source=input_source)
            title = full.get("title") or full.get("name") or mid
            started_at = (
                full.get("started_at") or full.get("startedAt") or full.get("start_time") or ""
            )
            date_prefix = str(started_at)[:10] if started_at else now_iso()[:10]
            fname = f"{date_prefix}--{_slugify(title)}--{short}.md"
            target = output_root / fname

            if dry_run:
                log.info("  DRY: would write %s (%d bytes)", target.relative_to(ROOT_DIR), len(md))
                continue

            output_root.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding="utf-8")
            log.info("  wrote %s", target.relative_to(ROOT_DIR))
            files_written.append(target)

            if started_at and (highest_started is None or str(started_at) > str(highest_started)):
                highest_started = str(started_at)

        if not dry_run and highest_started:
            state["last_seen_ts"] = highest_started
            _save_state(state)

        return RunResult(
            files_written=tuple(files_written),
            files_skipped=skipped,
            state_keys_touched=("last_seen_ts",) if not dry_run else (),
            message=(
                f"listed {len(summaries)} · wrote {len(files_written)} · "
                f"skipped {skipped} · since={since or '—'}"
            ),
        )
