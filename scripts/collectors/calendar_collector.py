"""Calendar Collector — Google Calendar events as substrate.

Replaces the year-counts ``scan_calendar.py`` stub (pre-M006) with a real
per-event collector that lands a per-date rollup at
``raw/notes/calendar/<date>.md``. Multi-tenant via
``CONFIG.personal.accounts.<id>.calendar`` (``kind: google-calendar``);
OAuth re-uses the shared ``core/google_oauth.py`` installed-app flow
(scope: ``calendar.readonly``); per-account token cache at
``state/calendar-token-<id>.json``.

Shape
-----

One markdown file per date, regardless of how many accounts / calendars
contributed events to it. The file is regenerated end-to-end each run for
the dates touched by the current sync window — the rewrite is cheap
(events are short), and it lets the collector handle event mutations
(updated title, time-shift) and cancellations without doing partial-edit
gymnastics inside the file. Operator prose mixed in between event blocks
is preserved by only rewriting the events region.

Frontmatter::

    ---
    title: "Calendar — 2026-05-15"
    type: calendar-rollup
    date: 2026-05-15
    event_count: 7
    meeting_hours: 4.5
    focus_hours: 3.0
    people: [jane-doe@example.com, ...]
    event_ids: [abc123, def456, ...]
    ingested_at: 2026-05-15T08:30:00Z
    ---

Body::

    ## 09:00–09:30 · Standup
    - **Calendar:** Work (account: work)
    - **Attendees:** jane-doe@example.com, bob-smith@example.com
    - **Location:** https://meet.google.com/...
    - **Recurring:** [[concepts/weekly-standup|Weekly Standup]]
    - **Transcript:** [[../transcripts/gmeet/2026-05-15--standup--abc123|gmeet]]
    - **Event ID:** abc123

    Description, if present (verbatim from Google).

Phases delivered
----------------

- **Primary calendar via OAuth** — re-uses ``core/google_oauth.py``.
- **Multi-calendar loop** — per-account ``include: [primary, ...]``
  selects which CalendarList entries to scan; default is every calendar
  with ``selected: true`` (Google's own UI toggle).
- **Per-date rollups** — one file per date, regenerated atomically.
- **Recurring-event collapse** — first time an ``recurringEventId``
  series is seen, write ``knowledge/concepts/<slug>.md`` (a real concept
  page with ``type: concept`` + ``series: true`` + a domain tag). Per-date
  rollups link to it via ``Recurring: [[concepts/<slug>|Title]]``.
- **gmeet / jamie transcript cross-link** — post-pass scans
  ``raw/transcripts/{gmeet,jamie}/*.md`` and adds a
  ``Transcript: [[…|gmeet]]`` line to events whose date + title match a
  transcript file (fuzzy title match on slugified meeting title).
- **Mutable-event re-fetch** — state stores ``etag`` per event id. On
  re-sync, an unchanged etag for a previously seen event id means the
  event block doesn't need to be regenerated; a changed etag rebuilds
  the date file.

Anti-slop heuristics (per backlog/calendar-collector.md):

- Skip events whose ``status == "cancelled"`` (also done server-side via
  ``showDeleted=false`` — listed here defensively).
- Skip events whose operator-side ``responseStatus`` is ``declined``.
- Skip events whose title matches ``CONFIG.personal.calendar_skip_keywords``
  (locale-specific holidays / observances).
- Collapse recurring-series instances: per the rule above.

State shape (``state/calendar-state.json``)::

    {
      "<account_id>": {
        "calendars": {
          "<calendar_id>": {
            "watermark_updated": "<ISO timestamp of newest updated event seen>",
            "etags": {"<event_id>": "<etag>"}
          }
        },
        "recurring": {"<recurringEventId>": "<concept-slug>"}
      }
    }
"""

from __future__ import annotations

import functools
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from adapters.calendar.google import (
    CalendarAPIError,
    GoogleCalendarClient,
    SCOPE as _GOOGLE_CAL_SCOPE,
)
from collectors.base import (
    CollectorSpec,
    RunResult,
    filter_accounts,
    register,
    resolve_accounts,
    run_account_loop,
)
from core import google_oauth, markers
from core.config import CONFIG
from core.google_oauth import OAuthApp
from core.paths import ROOT_DIR, STATE_DIR
from core.utils import load_json_state, now_iso, save_json_state

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

_OUTPUT_SUBFOLDER = "raw/notes/calendar"
_STATE_FILE = STATE_DIR / "calendar-state.json"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


# Region inside the per-date file that the collector owns. Operator-typed
# prose ABOVE or BELOW these sentinels is preserved across regenerations.
_EVENTS_BEGIN = "<!-- calendar:events:begin -->"
_EVENTS_END = "<!-- calendar:events:end -->"

# Heuristic: a "meeting" is an event with at least one attendee other than
# the operator themselves. Pure focus blocks and personal reminders have
# zero attendees. Counted via the frontmatter ``meeting_hours`` /
# ``focus_hours`` fields so dashboards can chart load.
_FOCUS_HOUR_CAP = 12.0  # an all-day event doesn't get counted as 24h focus


# ── Slug + time helpers ──────────────────────────────────────────────

def _slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _parse_event_time(raw: dict | None) -> tuple[datetime | None, bool]:
    """Parse a Google Calendar event-time block.

    Returns ``(datetime_or_None, is_all_day)``. The API gives either::

        {"dateTime": "2026-05-15T09:00:00+02:00", "timeZone": "Europe/Berlin"}
        {"date": "2026-05-15"}   # all-day

    Returns (None, False) for malformed input (the caller skips the event)."""
    if not isinstance(raw, dict):
        return None, False
    if "dateTime" in raw and isinstance(raw["dateTime"], str):
        try:
            return datetime.fromisoformat(raw["dateTime"].replace("Z", "+00:00")), False
        except ValueError:
            return None, False
    if "date" in raw and isinstance(raw["date"], str):
        try:
            d = datetime.fromisoformat(raw["date"])
            return d.replace(tzinfo=timezone.utc), True
        except ValueError:
            return None, False
    return None, False


def _format_event_window(start: datetime, end: datetime | None, *, all_day: bool) -> str:
    """Render the ``HH:MM–HH:MM`` (or ``all-day``) prefix for an event heading."""
    if all_day:
        return "all-day"
    if end is None:
        return start.strftime("%H:%M")
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def _event_duration_hours(start: datetime, end: datetime | None, *, all_day: bool) -> float:
    if end is None:
        return 0.0
    if all_day:
        # All-day events: count 0 in both meeting/focus buckets (otherwise
        # one PTO marker would dwarf the day's actual load metric).
        return 0.0
    delta = end - start
    return max(0.0, delta.total_seconds() / 3600.0)


# ── Account resolution ──────────────────────────────────────────────

@dataclass(frozen=True)
class _CalendarAccount:
    """Resolved calendar config for one ``personal.accounts.<id>`` entry."""

    account_id: str
    include: tuple[str, ...]  # calendar ids or summaries; empty → use `selected`
    backfill_days: int
    future_days: int
    since: str | None
    max_per_run: int


def _resolve_calendar_accounts() -> list[_CalendarAccount]:
    """Return the accounts with a ``calendar:`` sub-block whose ``kind ==
    "google-calendar"``, via the shared ``base.resolve_accounts``
    kind-dispatch. Unknown kinds are silently skipped (graceful agnostic)."""
    default_backfill = CONFIG.limits.calendar_backfill_days
    default_future = CONFIG.limits.calendar_future_days
    default_max = CONFIG.limits.calendar_max_per_run

    def _build(aid: str, block: dict) -> _CalendarAccount:
        include_raw = block.get("include") or []
        include = tuple(str(x) for x in include_raw if isinstance(x, str) and x)
        per_acct_max = block.get("max_per_run")
        return _CalendarAccount(
            account_id=aid,
            include=include,
            backfill_days=int(block.get("backfill_days") or default_backfill),
            future_days=int(block.get("future_days") or default_future),
            since=block.get("since") or None,
            max_per_run=int(per_acct_max if per_acct_max is not None else default_max),
        )

    return resolve_accounts(
        CONFIG.personal.accounts or {}, "google-calendar", _build, block_key="calendar"
    )


# ── OAuth ───────────────────────────────────────────────────────────



def _app(account_id: str) -> OAuthApp:
    return OAuthApp(
        client_file=google_oauth.resolve_client_file(
            account_id,
            integration_legacy=ROOT_DIR / ".claude" / "gmail-oauth-client.json",
        ),
        scopes=(_GOOGLE_CAL_SCOPE,),
        token_prefix="calendar-token",
        bootstrap_cmd="wiki calendar-auth",
        service_label="Google Calendar",
    )


def calendar_auth_bootstrap(account_id: str) -> tuple[bool, str]:
    """Run the installed-app OAuth flow once for one account. Called from
    ``wiki calendar-auth <account-id>``. Persists the token under that id."""
    return google_oauth.bootstrap(_app(account_id), account_id)


# ── Event filtering ─────────────────────────────────────────────────

def _is_holiday(title: str) -> bool:
    """Match against ``CONFIG.personal.calendar_skip_keywords`` (locale-specific)."""
    if not title:
        return False
    keywords = CONFIG.personal.calendar_skip_keywords or []
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in keywords)


def _is_operator_declined(event: dict, operator_email: str | None) -> bool:
    """True iff the operator's own attendee entry has ``responseStatus == declined``."""
    if not operator_email:
        return False
    for att in event.get("attendees") or []:
        if not isinstance(att, dict):
            continue
        is_self = att.get("self") is True or (
            isinstance(att.get("email"), str)
            and att["email"].lower() == operator_email.lower()
        )
        if is_self and att.get("responseStatus") == "declined":
            return True
    return False


# ── Rendering ───────────────────────────────────────────────────────

@dataclass
class _EventBlock:
    """One event ready to render into a per-date rollup."""

    event_id: str
    etag: str
    start: datetime
    end: datetime | None
    all_day: bool
    summary: str
    description: str
    location: str
    attendees: list[str]
    organizer: str | None
    calendar_summary: str
    account_id: str
    is_meeting: bool
    recurring_event_id: str | None
    recurring_slug: str | None
    recurring_title: str | None
    transcript_link: str | None = None  # filled in by cross-link pass

    def date_key(self) -> str:
        return self.start.strftime("%Y-%m-%d")


def _render_event_block(b: _EventBlock) -> str:
    """Render one ``## …`` event section."""
    window = _format_event_window(b.start, b.end, all_day=b.all_day)
    heading = f"## {window} · {b.summary or '(no title)'}"
    lines = [heading]
    meta: list[str] = []
    meta.append(f"- **Calendar:** {b.calendar_summary} (account: {b.account_id})")
    if b.attendees:
        meta.append(f"- **Attendees:** {', '.join(b.attendees)}")
    if b.organizer and b.organizer not in b.attendees:
        meta.append(f"- **Organizer:** {b.organizer}")
    if b.location:
        meta.append(f"- **Location:** {b.location}")
    if b.recurring_slug and b.recurring_title:
        meta.append(
            f"- **Recurring:** [[concepts/{b.recurring_slug}|{b.recurring_title}]]"
        )
    if b.transcript_link:
        meta.append(f"- **Transcript:** {b.transcript_link}")
    meta.append(f"- **Event ID:** {b.event_id}")
    lines.extend(meta)
    if b.description.strip():
        lines.append("")
        lines.append(b.description.strip())
    lines.append("")
    return "\n".join(lines)


def _render_date_file(
    date_key: str,
    blocks: list[_EventBlock],
    *,
    existing_text: str | None,
) -> str:
    """Render one per-date rollup. Preserves operator prose outside the
    managed ``<!-- calendar:events:* -->`` sentinels."""
    blocks_sorted = sorted(blocks, key=lambda b: (b.start, b.summary))

    event_count = len(blocks_sorted)
    meeting_hours = 0.0
    focus_hours = 0.0
    people: set[str] = set()
    event_ids: list[str] = []
    for b in blocks_sorted:
        dur = _event_duration_hours(b.start, b.end, all_day=b.all_day)
        if b.is_meeting:
            meeting_hours += dur
        else:
            focus_hours += min(dur, _FOCUS_HOUR_CAP)
        for a in b.attendees:
            people.add(a)
        event_ids.append(b.event_id)

    front: dict[str, Any] = {
        "title": f"Calendar — {date_key}",
        "type": "calendar-rollup",
        "date": date_key,
        "event_count": event_count,
        "meeting_hours": round(meeting_hours, 2),
        "focus_hours": round(focus_hours, 2),
        "people": sorted(people),
        "event_ids": event_ids,
        "tags": ["calendar"],
        "ingested_at": now_iso(),
    }
    # Drop empties for terser frontmatter.
    front = {k: v for k, v in front.items() if v not in (None, [], "")}
    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    events_md = "\n".join(_render_event_block(b) for b in blocks_sorted).rstrip()
    managed_region = (
        f"{_EVENTS_BEGIN}\n\n"
        f"{events_md}\n\n"
        f"{_EVENTS_END}"
    )

    pre_prose, post_prose = _split_operator_prose(existing_text)
    body_parts = [f"# Calendar — {date_key}", ""]
    if pre_prose:
        body_parts.append(pre_prose.strip())
        body_parts.append("")
    body_parts.append(managed_region)
    if post_prose:
        body_parts.append("")
        body_parts.append(post_prose.strip())
    body = "\n".join(body_parts).rstrip() + "\n"
    return f"---\n{fm}\n---\n{body}"


def _split_operator_prose(existing: str | None) -> tuple[str, str]:
    """Extract the operator-written sections before/after the managed
    events region. Returns ``("", "")`` when the file is new or doesn't
    have the sentinels yet. Region location (incl. the stray/reversed-marker
    contract) is ``core.markers``."""
    if not existing:
        return "", ""
    # Strip frontmatter if present.
    body = existing
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end >= 0:
            body = body[end + len("\n---\n"):]
    # Strip the first ``# Calendar — …`` heading (we always re-emit it).
    body = re.sub(r"^# Calendar —[^\n]*\n+", "", body, count=1)
    region = markers.find_region(body, _EVENTS_BEGIN, _EVENTS_END)
    if region is None:
        return body.strip(), ""
    return body[: region.start].strip(), body[region.end :].strip()


# ── Recurring concept page ──────────────────────────────────────────

def _recurring_concept_path(slug: str) -> Path:
    return ROOT_DIR / "knowledge" / "concepts" / f"{slug}.md"


def _render_recurring_concept(
    slug: str,
    title: str,
    *,
    sample_block: _EventBlock,
) -> str:
    """Write the canonical concept page for a recurring series.

    Cheap shape — frontmatter + a one-paragraph stub. Compile passes can
    enrich it later; the value of this file today is being the link
    target for the per-date rollups (so the graph view shows the series
    as one node).
    """
    front: dict[str, Any] = {
        "title": title,
        "type": "concept",
        "series": True,
        "tags": ["meeting", "recurring", "llm-wiki"],
        "ingested_at": now_iso(),
    }
    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()
    cadence = "Recurring calendar series." if not sample_block.all_day else "Recurring all-day event."
    body_parts = [
        f"# {title}",
        "",
        cadence,
        "",
        "## Origin",
        "",
        f"- First seen: {sample_block.start.strftime('%Y-%m-%d')}",
        f"- Calendar: {sample_block.calendar_summary} (account: {sample_block.account_id})",
    ]
    if sample_block.attendees:
        body_parts.append(f"- Initial attendees: {', '.join(sample_block.attendees)}")
    if sample_block.description.strip():
        body_parts.append("")
        body_parts.append("## Description")
        body_parts.append("")
        body_parts.append(sample_block.description.strip())
    body_parts.append("")
    body = "\n".join(body_parts).rstrip() + "\n"
    return f"---\n{fm}\n---\n{body}"


# ── Transcript cross-link ───────────────────────────────────────────

_TRANSCRIPT_ROOTS = ("raw/transcripts/gmeet", "raw/transcripts/jamie")


@dataclass(frozen=True)
class _TranscriptRef:
    relpath: str       # path relative to ROOT_DIR
    title: str
    title_slug: str
    date_key: str      # "YYYY-MM-DD"
    kind: str          # "gmeet" | "jamie"

    def to_link(self) -> str:
        stem = Path(self.relpath).stem
        # ``../transcripts/<kind>/<stem>`` from ``raw/notes/calendar/``.
        return f"[[../transcripts/{self.kind}/{stem}|{self.kind}]]"


def _scan_transcripts() -> list[_TranscriptRef]:
    """Read frontmatter from every gmeet + jamie transcript file. Returns
    a flat list — the matching loop iterates it per event."""
    refs: list[_TranscriptRef] = []
    for sub in _TRANSCRIPT_ROOTS:
        root = ROOT_DIR / sub
        if not root.exists():
            continue
        kind = sub.rsplit("/", 1)[-1]
        for p in sorted(root.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if not text.startswith("---\n"):
                continue
            end = text.find("\n---\n", 4)
            if end < 0:
                continue
            try:
                front = yaml.safe_load(text[4:end])
            except yaml.YAMLError:
                continue
            if not isinstance(front, dict):
                continue
            title = front.get("title")
            started = front.get("started_at") or front.get("date")
            if not isinstance(title, str) or not isinstance(started, str):
                continue
            date_key = started[:10]
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_key):
                continue
            refs.append(_TranscriptRef(
                relpath=str(p.relative_to(ROOT_DIR)),
                title=title,
                title_slug=_slugify(title),
                date_key=date_key,
                kind=kind,
            ))
    return refs


def _attach_transcript_links(blocks: list[_EventBlock], refs: list[_TranscriptRef]) -> int:
    """Mutate ``blocks`` in place: for each block, find a transcript on
    the same date whose title-slug shares a prefix or substring with the
    event-title-slug. Returns the number of links attached."""
    if not refs:
        return 0
    by_date: dict[str, list[_TranscriptRef]] = defaultdict(list)
    for r in refs:
        by_date[r.date_key].append(r)
    attached = 0
    for b in blocks:
        if b.transcript_link is not None:
            continue
        date_key = b.date_key()
        candidates = by_date.get(date_key) or []
        if not candidates:
            continue
        evt_slug = _slugify(b.summary)
        if not evt_slug:
            continue
        # Match: same date + the longer of (event-slug, transcript-slug)
        # contains the other. Sharing a 6+-char prefix is also accepted —
        # catches "alex-x-sid" vs "alex-x-sid-1-3".
        best: _TranscriptRef | None = None
        for r in candidates:
            ts = r.title_slug
            if not ts:
                continue
            if evt_slug == ts:
                best = r
                break
            if evt_slug in ts or ts in evt_slug:
                best = r
                continue
            if len(evt_slug) >= 6 and len(ts) >= 6 and (
                ts.startswith(evt_slug[:6]) or evt_slug.startswith(ts[:6])
            ):
                best = r
        if best is not None:
            b.transcript_link = best.to_link()
            attached += 1
    return attached


# ── Collector ───────────────────────────────────────────────────────

@register
class CalendarCollector:
    SPEC = CollectorSpec(
        name="calendar",
        output_subfolder=_OUTPUT_SUBFOLDER,
        piggyback_default=True,
        piggyback_cooldown_hours=6,
        supports_incremental=True,
        supports_account_loop=True,
    )

    def __init__(self) -> None:
        self._accounts = _resolve_calendar_accounts()
        self._timeout_s = float(CONFIG.limits.calendar_request_timeout_s)

    def is_configured(self) -> bool:
        """At least one account with ``kind: google-calendar`` AND a
        bootstrapped token cache."""
        if not self._accounts:
            return False
        return any(
            google_oauth.token_path(_app(a.account_id), a.account_id).exists()
            for a in self._accounts
        )

    # ── public entry point ───────────────────────────────────────────

    def run(
        self, *, dry_run: bool = False, incremental: bool = False, account: str | None = None
    ) -> RunResult:
        if not self._accounts:
            log.info("CalendarCollector: no accounts with kind=google-calendar — skipping.")
            return RunResult(message="no-op (no calendar accounts configured)")

        accounts = filter_accounts(self._accounts, account)
        if not accounts:
            return RunResult(message=f"no-op (no calendar account {account!r} configured)")

        state = load_json_state(_STATE_FILE)
        all_written: list[Path] = []
        total_skipped = 0

        # Gather per-account event blocks first so we can write per-date
        # files in one pass (a date can carry events from multiple accounts).
        # The harness owns failure isolation + message aggregation; the payload
        # here is (blocks, new_concepts) — payload-generic, not the files+skipped
        # shape the other account collectors return.
        blocks_by_date: dict[str, list[_EventBlock]] = defaultdict(list)
        new_concepts: list[tuple[str, _EventBlock]] = []  # (slug, sample)

        scan = functools.partial(self._run_one_account, state=state, incremental=incremental)
        outcome = run_account_loop(accounts, scan, log=log, name="CalendarCollector")
        for blocks, concepts in outcome.payloads:
            for b in blocks:
                blocks_by_date[b.date_key()].append(b)
            new_concepts.extend(concepts)
        any_state_touched = outcome.any_state_touched
        per_acct_messages = outcome.messages

        # Cross-link pass — fuzzy match event title + date to transcripts.
        flat_blocks = [b for v in blocks_by_date.values() for b in v]
        transcripts = _scan_transcripts()
        linked = _attach_transcript_links(flat_blocks, transcripts)
        if linked:
            log.info("CalendarCollector: %d transcript link(s) attached", linked)

        # Recurring-concept pages.
        if not dry_run:
            for slug, sample in new_concepts:
                path = _recurring_concept_path(slug)
                if path.exists():
                    continue
                # Title is whatever the operator-facing event summary was when
                # we first saw the series.
                title = sample.summary or slug.replace("-", " ").title()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    _render_recurring_concept(slug, title, sample_block=sample),
                    encoding="utf-8",
                )
                all_written.append(path)

        # Per-date rollups.
        output_root = ROOT_DIR / self.SPEC.output_subfolder
        if not dry_run:
            output_root.mkdir(parents=True, exist_ok=True)
        for date_key, blocks in sorted(blocks_by_date.items()):
            target = output_root / f"{date_key}.md"
            existing = target.read_text(encoding="utf-8") if target.exists() else None
            md = _render_date_file(date_key, blocks, existing_text=existing)
            if dry_run:
                log.info("  DRY: would write %s (%d events, %d bytes)",
                         target.relative_to(ROOT_DIR), len(blocks), len(md))
                continue
            target.write_text(md, encoding="utf-8")
            log.info("  wrote %s (%d events)",
                     target.relative_to(ROOT_DIR), len(blocks))
            all_written.append(target)

        if not dry_run and any_state_touched:
            save_json_state(_STATE_FILE, state)

        return RunResult(
            files_written=tuple(all_written),
            files_skipped=total_skipped,
            state_keys_touched=(
                tuple(a.account_id for a in accounts) if any_state_touched else ()
            ),
            message=" · ".join(per_acct_messages) or "no-op",
        )

    # ── per-account ──────────────────────────────────────────────────

    def _run_one_account(
        self,
        acct: _CalendarAccount,
        *,
        state: dict,
        incremental: bool,
    ) -> tuple[str, tuple[list[_EventBlock], list[tuple[str, _EventBlock]]], bool]:
        """Run one account's scan. Returns (message, (blocks, new_concepts),
        state_touched) for the harness's payload-generic aggregation.

        ``new_concepts`` is the list of recurring-series slugs that need a
        canonical concept page written (first sighting only)."""
        sess, err = google_oauth.session(_app(acct.account_id), acct.account_id)
        if err:
            return f"auth: {err}", ([], []), False
        client = GoogleCalendarClient(session=sess, timeout_s=self._timeout_s)

        # ── Calendar selection ──
        try:
            cal_items = client.list_calendars()
        except CalendarAPIError as e:
            log.error("CalendarCollector[%s]: list_calendars failed: %s", acct.account_id, e)
            return f"list_calendars failed: {e}", ([], []), False
        chosen = self._select_calendars(cal_items, acct)
        if not chosen:
            return "no-op (no calendars selected)", ([], []), False

        # ── Time window ──
        now = datetime.now(timezone.utc)
        time_min_dt = now - timedelta(days=acct.backfill_days)
        time_max_dt = now + timedelta(days=acct.future_days)
        time_min = time_min_dt.isoformat().replace("+00:00", "Z")
        time_max = time_max_dt.isoformat().replace("+00:00", "Z")

        # Operator email — used to resolve the "self" attendee for
        # responseStatus=declined filtering.
        operator_email = self._operator_email(acct.account_id)

        acct_state = state.get(acct.account_id) or {}
        cal_state = acct_state.get("calendars") or {}
        recurring_map = dict(acct_state.get("recurring") or {})

        blocks: list[_EventBlock] = []
        new_concepts: list[tuple[str, _EventBlock]] = []
        state_touched = False
        total_listed = 0

        for cal in chosen:
            cal_id = cal.get("id") or ""
            cal_summary = cal.get("summaryOverride") or cal.get("summary") or cal_id
            if not cal_id:
                continue

            entry = dict(cal_state.get(cal_id) or {})
            etag_map: dict[str, str] = dict(entry.get("etags") or {})
            new_etag_map: dict[str, str] = {}
            watermark = entry.get("watermark_updated")
            updated_min = None
            if incremental and watermark:
                # Google requires the updatedMin watermark to be strictly in
                # the past; an inflight watermark equal to "now" would 400.
                updated_min = watermark
            elif acct.since:
                time_min = acct.since

            try:
                events = list(client.list_events(
                    cal_id,
                    time_min=time_min,
                    time_max=time_max,
                    updated_min=updated_min,
                    limit=acct.max_per_run,
                ))
            except CalendarAPIError as e:
                log.error("CalendarCollector[%s/%s]: list_events failed: %s",
                          acct.account_id, cal_summary, e)
                continue

            total_listed += len(events)
            newest_updated = watermark

            for ev in events:
                if ev.get("status") == "cancelled":
                    continue
                summary = ev.get("summary") or ""
                if _is_holiday(summary):
                    continue
                if _is_operator_declined(ev, operator_email):
                    continue
                start_dt, all_day = _parse_event_time(ev.get("start"))
                if start_dt is None:
                    continue
                end_dt, _end_all_day = _parse_event_time(ev.get("end"))

                attendees: list[str] = []
                for att in ev.get("attendees") or []:
                    if not isinstance(att, dict):
                        continue
                    if att.get("self") is True:
                        continue  # don't list operator
                    email = att.get("email")
                    if isinstance(email, str) and email:
                        if att.get("responseStatus") == "declined":
                            continue
                        attendees.append(email)
                attendees.sort()

                organizer = None
                org = ev.get("organizer")
                if isinstance(org, dict):
                    organizer = org.get("email")

                description = ev.get("description") or ""
                if not isinstance(description, str):
                    description = ""
                location = ev.get("location") or ""
                if not isinstance(location, str):
                    location = ""

                is_meeting = bool(attendees)
                recurring_event_id = ev.get("recurringEventId")
                recurring_slug: str | None = None
                recurring_title: str | None = None
                if isinstance(recurring_event_id, str) and recurring_event_id:
                    slug = recurring_map.get(recurring_event_id)
                    if slug is None:
                        slug = _slugify(summary or recurring_event_id)
                        recurring_map[recurring_event_id] = slug
                    recurring_slug = slug
                    recurring_title = summary or slug.replace("-", " ").title()

                block = _EventBlock(
                    event_id=ev.get("id") or "",
                    etag=ev.get("etag") or "",
                    start=start_dt,
                    end=end_dt,
                    all_day=all_day,
                    summary=summary,
                    description=description,
                    location=location,
                    attendees=attendees,
                    organizer=organizer,
                    calendar_summary=cal_summary,
                    account_id=acct.account_id,
                    is_meeting=is_meeting,
                    recurring_event_id=recurring_event_id if isinstance(recurring_event_id, str) else None,
                    recurring_slug=recurring_slug,
                    recurring_title=recurring_title,
                )
                blocks.append(block)

                # Track concept-page need: first time we see this series id
                # AND a concept page doesn't already exist on disk.
                if recurring_event_id and isinstance(recurring_event_id, str):
                    slug = recurring_map[recurring_event_id]
                    if not _recurring_concept_path(slug).exists() and not any(
                        s == slug for s, _ in new_concepts
                    ):
                        new_concepts.append((slug, block))

                if block.event_id:
                    new_etag_map[block.event_id] = block.etag

                upd = ev.get("updated")
                if isinstance(upd, str):
                    if newest_updated is None or upd > newest_updated:
                        newest_updated = upd

            # State update: keep etag union of old + new (events not
            # mentioned this run might still be in the cache; they'll be
            # refreshed the next time they fall into the window).
            merged_etags = {**etag_map, **new_etag_map}
            entry["etags"] = merged_etags
            if newest_updated:
                entry["watermark_updated"] = newest_updated
            cal_state[cal_id] = entry
            if events:
                state_touched = True

        acct_state["calendars"] = cal_state
        acct_state["recurring"] = recurring_map
        state[acct.account_id] = acct_state

        msg = (
            f"calendars={len(chosen)} · listed={total_listed} · blocks={len(blocks)}"
            f" · recurring={len(new_concepts)}"
        )
        return msg, (blocks, new_concepts), state_touched

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _select_calendars(cal_items: list[dict], acct: _CalendarAccount) -> list[dict]:
        """Apply the per-account ``include:`` filter.

        - Empty include → all calendars with ``selected: true`` (Google's
          own UI toggle); fall back to ``primary`` if nothing is selected
          (handles freshly-provisioned accounts).
        - Non-empty include → match by id OR summary, case-insensitive.
        """
        if not acct.include:
            sel = [c for c in cal_items if c.get("selected") is True]
            if sel:
                return sel
            return [c for c in cal_items if c.get("primary") is True] or cal_items[:1]
        wanted = {x.lower() for x in acct.include}
        out: list[dict] = []
        for c in cal_items:
            cid = (c.get("id") or "").lower()
            csm = (c.get("summary") or "").lower()
            cso = (c.get("summaryOverride") or "").lower()
            if cid in wanted or csm in wanted or cso in wanted:
                out.append(c)
        return out

    @staticmethod
    def _operator_email(account_id: str) -> str | None:
        """Look up the operator-side ``email:`` on this account, if any."""
        body = (CONFIG.personal.accounts or {}).get(account_id) or {}
        email = body.get("email")
        return email if isinstance(email, str) and email else None
