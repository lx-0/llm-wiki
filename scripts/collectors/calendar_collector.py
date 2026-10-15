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
contributed events to it. Every run lists the whole window (``backfill_days``
back, ``future_days`` ahead) and renders each date of it from ALL of that
date's events, so mutations (updated title, time-shift) and cancellations
need no partial-edit gymnastics inside the file; a file is written only when
its content changed. Operator prose mixed in between event blocks is
preserved by only rewriting the events region.

A date is rewritten only from a complete listing — every configured account
and calendar fetched this run, the date fully inside the window, no calendar
capped by ``max_per_run`` before it. Otherwise the rollups stay as they are
and the run says why: an incremental listing (``updatedMin``) once rewrote
each touched date from its changed events alone, and every unchanged event of
that date vanished (lxw 2026-06-11: event_count 6 → 1).

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
- **Whole-window re-list** — see "Shape": no delta sync, no per-event cache.
  An event that appears in two selected calendars (or two accounts) under the
  same id is rendered once.

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
        "recurring": {"<recurringEventId>": "<concept-slug>"}
      }
    }

(The per-calendar ``watermark_updated`` / ``etags`` cache of the delta-sync
design is dropped from an account's entry on its next run.)
"""

from __future__ import annotations

import functools
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from adapters.calendar.google import (
    SCOPE as _GOOGLE_CAL_SCOPE,
)
from adapters.calendar.google import (
    CalendarAPIError,
    GoogleCalendarClient,
)
from collectors.base import (
    CollectorSpec,
    RunResult,
    filter_accounts,
    register,
    resolve_accounts,
    run_account_loop,
)
from collectors.calendar_render import (
    _EventBlock,
    _render_date_file,
    _render_recurring_concept,
    _same_rollup,
)
from core import frontmatter, google_oauth
from core.config import CONFIG
from core.google_oauth import OAuthApp
from core.paths import ROOT_DIR, STATE_DIR
from core.utils import load_json_state, save_json_state, slugify

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

_OUTPUT_SUBFOLDER = "raw/notes/calendar"
_STATE_FILE = STATE_DIR / "calendar-state.json"

_DATE_STEM = re.compile(r"\d{4}-\d{2}-\d{2}")  # a rollup's filename stem


# ── Time helpers ─────────────────────────────────────────────────────
# (slugs come from `core.utils.slugify(..., ascii_only=True)` — the filename grammar)


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
            return d.replace(tzinfo=UTC), True
        except ValueError:
            return None, False
    return None, False


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
            isinstance(att.get("email"), str) and att["email"].lower() == operator_email.lower()
        )
        if is_self and att.get("responseStatus") == "declined":
            return True
    return False


# ── Recurring concept page ──────────────────────────────────────────


def _recurring_concept_path(slug: str) -> Path:
    return ROOT_DIR / "knowledge" / "concepts" / f"{slug}.md"


# ── Transcript cross-link ───────────────────────────────────────────

_TRANSCRIPT_ROOTS = ("raw/transcripts/gmeet", "raw/transcripts/jamie")


@dataclass(frozen=True)
class _TranscriptRef:
    relpath: str  # path relative to ROOT_DIR
    title: str
    title_slug: str
    date_key: str  # "YYYY-MM-DD"
    kind: str  # "gmeet" | "jamie"

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
            front, _body = frontmatter.parse(text)
            if not front:  # no fence, malformed, or not a mapping — the seam says {}
                continue
            title = front.get("title")
            started = front.get("started_at") or front.get("date")
            if not isinstance(title, str) or not isinstance(started, str):
                continue
            date_key = started[:10]
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_key):
                continue
            refs.append(
                _TranscriptRef(
                    relpath=str(p.relative_to(ROOT_DIR)),
                    title=title,
                    title_slug=slugify(title, max_len=60, ascii_only=True),
                    date_key=date_key,
                    kind=kind,
                )
            )
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
        evt_slug = slugify(b.summary, max_len=60, ascii_only=True)
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
            if (
                len(evt_slug) >= 6
                and len(ts) >= 6
                and (ts.startswith(evt_slug[:6]) or evt_slug.startswith(ts[:6]))
            ):
                best = r
        if best is not None:
            b.transcript_link = best.to_link()
            attached += 1
    return attached


# ── Per-account scan ────────────────────────────────────────────────


@dataclass(frozen=True)
class _Coverage:
    """What one account's scan vouches for: every event dated ``first`` …
    ``last`` was listed — unless ``complete`` is False (the account or one of
    its calendars could not be fetched) — up to the day before ``cut``, the
    date at which a calendar's listing hit ``max_per_run``."""

    account_id: str
    first: str  # YYYY-MM-DD
    last: str
    complete: bool = True
    cut: str | None = None


def _window_dates(acct: _CalendarAccount, *, incremental: bool) -> tuple[date, date]:
    """The dates one run lists whole: ``backfill_days`` back to ``future_days``
    ahead of today (UTC) — or, on a full (not incremental) run, from the
    account's configured ``since``."""
    now = datetime.now(UTC)
    first = (now - timedelta(days=acct.backfill_days)).date()
    if not incremental and acct.since:
        try:
            first = datetime.fromisoformat(acct.since.replace("Z", "+00:00")).date()
        except ValueError:
            log.warning("CalendarCollector[%s]: unparseable since %r", acct.account_id, acct.since)
    return first, (now + timedelta(days=acct.future_days)).date()


def _utc_midnight(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _rollup_span(
    coverages: list[_Coverage], *, failed: list[str], unlisted: list[str]
) -> tuple[tuple[str, str] | None, str]:
    """The dates whose rollups this run can rewrite, or None and why not. A
    date's file holds the events of every account, so any account missing from
    the listing — not asked for, failed, or with a calendar it could not list —
    leaves every rollup as it is (the next complete run catches up)."""
    if unlisted:
        return None, f"this run did not list {', '.join(unlisted)}"
    partial = sorted({*failed, *(c.account_id for c in coverages if not c.complete)})
    if partial:
        return None, f"{', '.join(partial)} not fully listed"
    if not coverages:
        return None, "no account was listed"
    first = max(c.first for c in coverages)
    last = min(c.last for c in coverages)
    cuts = [c.cut for c in coverages if c.cut]
    if cuts:
        last = min(last, (date.fromisoformat(min(cuts)) - timedelta(days=1)).isoformat())
    if first > last:
        return None, "no date is fully listed"
    return (first, last), ""


@dataclass
class _CalendarScan:
    """The accumulators of one account's scan, shared by the per-calendar phase.

    The fetch window reaches a day past the account's dates on each side, so an
    edge date is listed whole whatever the event's UTC offset (date keys use the
    event's own offset)."""

    time_min: str
    time_max: str
    operator_email: str | None
    recurring_map: dict[str, str]
    blocks: list[_EventBlock] = field(default_factory=list)
    new_concepts: list[tuple[str, _EventBlock]] = field(default_factory=list)
    total_listed: int = 0
    complete: bool = True
    cut: str | None = None


def _fetch_events(
    client: GoogleCalendarClient,
    cal_id: str,
    *,
    acct: _CalendarAccount,
    cal_summary: str,
    time_min: str,
    time_max: str,
) -> list[dict] | None:
    """The fetch phase for one calendar; None when the API call failed (logged —
    the calendar is skipped this run)."""
    try:
        return list(
            client.list_events(
                cal_id,
                time_min=time_min,
                time_max=time_max,
                limit=acct.max_per_run,
            )
        )
    except CalendarAPIError as e:
        log.error(
            "CalendarCollector[%s/%s]: list_events failed: %s",
            acct.account_id,
            cal_summary,
            e,
        )
        return None


def _event_block(
    ev: dict,
    *,
    cal_summary: str,
    account_id: str,
    operator_email: str | None,
    recurring_map: dict[str, str],
) -> _EventBlock | None:
    """The transform phase for one event: None when the event is cancelled, a
    holiday, declined by the operator or has an unparseable start; otherwise the
    block, with the recurring series registered in ``recurring_map`` on first
    sight."""
    if ev.get("status") == "cancelled":
        return None
    summary = ev.get("summary") or ""
    if _is_holiday(summary):
        return None
    if _is_operator_declined(ev, operator_email):
        return None
    start_dt, all_day = _parse_event_time(ev.get("start"))
    if start_dt is None:
        return None
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
            slug = slugify(summary or recurring_event_id, max_len=60, ascii_only=True)
            recurring_map[recurring_event_id] = slug
        recurring_slug = slug
        recurring_title = summary or slug.replace("-", " ").title()

    return _EventBlock(
        event_id=ev.get("id") or "",
        start=start_dt,
        end=end_dt,
        all_day=all_day,
        summary=summary,
        description=description,
        location=location,
        attendees=attendees,
        organizer=organizer,
        calendar_summary=cal_summary,
        account_id=account_id,
        is_meeting=is_meeting,
        recurring_event_id=recurring_event_id if isinstance(recurring_event_id, str) else None,
        recurring_slug=recurring_slug,
        recurring_title=recurring_title,
    )


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

        # Gather every account's events first: a date's file carries the events
        # of every account, so it is rendered once all of them are listed. The
        # harness owns failure isolation + message aggregation; the payload is
        # (blocks, new_concepts, coverage) — payload-generic, not the
        # files+skipped shape the other account collectors return.
        blocks: list[_EventBlock] = []
        new_concepts: list[tuple[str, _EventBlock]] = []  # (slug, sample)
        coverages: list[_Coverage] = []

        scan = functools.partial(self._run_one_account, state=state, incremental=incremental)
        outcome = run_account_loop(accounts, scan, log=log, name="CalendarCollector")
        for acct_blocks, concepts, coverage in outcome.payloads:
            blocks.extend(acct_blocks)
            new_concepts.extend(concepts)
            coverages.append(coverage)
        messages = list(outcome.messages)

        # Cross-link pass — fuzzy match event title + date to transcripts.
        linked = _attach_transcript_links(blocks, _scan_transcripts())
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

        # Per-date rollups — only from a listing that holds every event of the date.
        span, why_not = _rollup_span(
            coverages,
            failed=outcome.error_ids,
            unlisted=[a.account_id for a in self._accounts if a not in accounts],
        )
        unchanged = 0
        if span is None:
            log.warning("CalendarCollector: rollups not rewritten — %s", why_not)
            messages.append(f"rollups not rewritten: {why_not}")
        else:
            written, unchanged = self._write_rollups(blocks, span, dry_run=dry_run)
            all_written.extend(written)

        if not dry_run and outcome.any_state_touched:
            save_json_state(_STATE_FILE, state)

        return RunResult(
            files_written=tuple(all_written),
            files_skipped=unchanged,
            state_keys_touched=(
                tuple(a.account_id for a in accounts) if outcome.any_state_touched else ()
            ),
            message=" · ".join(messages) or "no-op",
        )

    def _write_rollups(
        self, blocks: list[_EventBlock], span: tuple[str, str], *, dry_run: bool
    ) -> tuple[list[Path], int]:
        """Render every date of ``span`` that has events or a file — each from
        all of its events, one block per event id (the same event can sit in
        two calendars) — and write the ones whose content changed. A date whose
        events are all gone keeps its file with an empty events region.
        Returns (written, unchanged)."""
        first, last = span
        output_root = ROOT_DIR / self.SPEC.output_subfolder
        by_date: dict[str, dict[str, _EventBlock]] = defaultdict(dict)
        for b in blocks:
            key = b.date_key()
            if first <= key <= last:
                by_date[key].setdefault(b.event_id or f"#{len(by_date[key])}", b)
        if output_root.is_dir():
            for path in output_root.glob("*.md"):
                if _DATE_STEM.fullmatch(path.stem) and first <= path.stem <= last:
                    by_date.setdefault(path.stem, {})
        elif not dry_run:
            output_root.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        unchanged = 0
        for date_key, events in sorted(by_date.items()):
            target = output_root / f"{date_key}.md"
            existing = target.read_text(encoding="utf-8") if target.exists() else None
            md = _render_date_file(date_key, list(events.values()), existing_text=existing)
            if existing is not None and _same_rollup(existing, md):
                unchanged += 1
                continue
            if dry_run:
                log.info(
                    "  DRY: would write %s (%d events, %d bytes)",
                    target.relative_to(ROOT_DIR),
                    len(events),
                    len(md),
                )
                continue
            target.write_text(md, encoding="utf-8")
            log.info("  wrote %s (%d events)", target.relative_to(ROOT_DIR), len(events))
            written.append(target)
        return written, unchanged

    # ── per-account ──────────────────────────────────────────────────

    def _run_one_account(
        self,
        acct: _CalendarAccount,
        *,
        state: dict,
        incremental: bool,
    ) -> tuple[str, tuple[list[_EventBlock], list[tuple[str, _EventBlock]], _Coverage], bool]:
        """Run one account's scan. Returns (message, (blocks, new_concepts,
        coverage), state_touched) for the harness's payload-generic aggregation.

        ``new_concepts`` is the list of recurring-series slugs that need a
        canonical concept page written (first sighting only); ``coverage`` says
        which dates the listing vouches for (``run()`` rewrites no rollup from a
        partial one).

        The phases: the window → the calendars → per calendar ``_scan_calendar``
        (``_fetch_events`` → ``_event_block`` per event) → the account state +
        message. The write phase (per-date files, concept pages) is ``run()``'s,
        once every account has been scanned."""
        first, last = _window_dates(acct, incremental=incremental)
        partial = _Coverage(acct.account_id, first.isoformat(), last.isoformat(), complete=False)
        sess, err = google_oauth.session(_app(acct.account_id), acct.account_id)
        if err:
            return f"auth: {err}", ([], [], partial), False
        client = GoogleCalendarClient(session=sess, timeout_s=self._timeout_s)

        # ── Calendar selection ──
        try:
            cal_items = client.list_calendars()
        except CalendarAPIError as e:
            log.error("CalendarCollector[%s]: list_calendars failed: %s", acct.account_id, e)
            return f"list_calendars failed: {e}", ([], [], partial), False
        chosen = self._select_calendars(cal_items, acct)
        if not chosen:
            whole = _Coverage(acct.account_id, first.isoformat(), last.isoformat())
            return "no-op (no calendars selected)", ([], [], whole), False

        acct_state = state.get(acct.account_id) or {}
        recurring_before = dict(acct_state.get("recurring") or {})
        scan = _CalendarScan(
            time_min=_utc_midnight(first - timedelta(days=1)),
            time_max=_utc_midnight(last + timedelta(days=2)),
            # Operator email — used to resolve the "self" attendee for
            # responseStatus=declined filtering.
            operator_email=self._operator_email(acct.account_id),
            recurring_map=dict(recurring_before),
        )

        for cal in chosen:
            self._scan_calendar(client, cal, acct, scan=scan)

        # The delta-sync cache (per-calendar watermark + etags) is retired.
        dropped_cache = acct_state.pop("calendars", None) is not None
        acct_state["recurring"] = scan.recurring_map
        state[acct.account_id] = acct_state

        msg = (
            f"calendars={len(chosen)} · listed={scan.total_listed} · blocks={len(scan.blocks)}"
            f" · recurring={len(scan.new_concepts)}"
        )
        coverage = _Coverage(
            acct.account_id, first.isoformat(), last.isoformat(), scan.complete, scan.cut
        )
        touched = dropped_cache or scan.recurring_map != recurring_before
        return msg, (scan.blocks, scan.new_concepts, coverage), touched

    @staticmethod
    def _scan_calendar(
        client: GoogleCalendarClient,
        cal: dict,
        acct: _CalendarAccount,
        *,
        scan: _CalendarScan,
    ) -> None:
        """One calendar: the whole window listed, the events through
        ``_event_block``; a failed fetch marks the scan incomplete, a capped
        listing records the date it stopped in."""
        cal_id = cal.get("id") or ""
        cal_summary = cal.get("summaryOverride") or cal.get("summary") or cal_id
        if not cal_id:
            return

        events = _fetch_events(
            client,
            cal_id,
            acct=acct,
            cal_summary=cal_summary,
            time_min=scan.time_min,
            time_max=scan.time_max,
        )
        if events is None:
            scan.complete = False
            return

        scan.total_listed += len(events)
        if acct.max_per_run > 0 and len(events) >= acct.max_per_run:
            # The listing runs in start order, so the cap ends it partway into a
            # date: that date and every later one are only partly listed.
            last_start, _ = _parse_event_time(events[-1].get("start"))
            cut = last_start.strftime("%Y-%m-%d") if last_start else scan.time_min[:10]
            scan.cut = min(cut, scan.cut) if scan.cut else cut
            log.warning(
                "CalendarCollector[%s/%s]: listing capped at max_per_run=%d on %s — "
                "rollups from that date on are not rewritten",
                acct.account_id,
                cal_summary,
                acct.max_per_run,
                cut,
            )

        for ev in events:
            block = _event_block(
                ev,
                cal_summary=cal_summary,
                account_id=acct.account_id,
                operator_email=scan.operator_email,
                recurring_map=scan.recurring_map,
            )
            if block is None:
                continue
            scan.blocks.append(block)

            # Track concept-page need: first time we see this series id
            # AND a concept page doesn't already exist on disk.
            recurring_event_id = ev.get("recurringEventId")
            if recurring_event_id and isinstance(recurring_event_id, str):
                slug = scan.recurring_map[recurring_event_id]
                if not _recurring_concept_path(slug).exists() and not any(
                    s == slug for s, _ in scan.new_concepts
                ):
                    scan.new_concepts.append((slug, block))

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
