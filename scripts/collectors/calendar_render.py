"""The calendar collector's renderer — the event model and the markdown it becomes,
with no paths and no API. ``collectors/calendar_collector.py`` lists the events and
decides which dates to write; this module turns one date's events into the text of
``raw/notes/calendar/<date>.md`` and a recurring series into its concept page.

Split out of the collector when the collector reached the 1,000-line module limit
(M033-S05-T06); every name moved verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yaml

from core import frontmatter, markers
from core.utils import now_iso

# Region inside the per-date file that the collector owns. Operator-typed
# prose ABOVE or BELOW these sentinels is preserved across regenerations.
_EVENTS_BEGIN = "<!-- calendar:events:begin -->"
_EVENTS_END = "<!-- calendar:events:end -->"

_INGESTED_AT = re.compile(r"^ingested_at: .*$", re.MULTILINE)

# Heuristic: a "meeting" is an event with at least one attendee other than
# the operator themselves. Pure focus blocks and personal reminders have
# zero attendees. Counted via the frontmatter ``meeting_hours`` /
# ``focus_hours`` fields so dashboards can chart load.
_FOCUS_HOUR_CAP = 12.0  # an all-day event doesn't get counted as 24h focus


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


@dataclass
class _EventBlock:
    """One event ready to render into a per-date rollup."""

    event_id: str
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
        meta.append(f"- **Recurring:** [[concepts/{b.recurring_slug}|{b.recurring_title}]]")
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
    managed_region = f"{_EVENTS_BEGIN}\n\n{events_md}\n\n{_EVENTS_END}"

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
    # Strip frontmatter if present (the seam's fence grammar; no fence → whole text).
    _block, body = frontmatter.split_fence(existing)
    # Strip the first ``# Calendar — …`` heading (we always re-emit it).
    body = re.sub(r"^# Calendar —[^\n]*\n+", "", body, count=1)
    region = markers.find_region(body, _EVENTS_BEGIN, _EVENTS_END)
    if region is None:
        return body.strip(), ""
    return body[: region.start].strip(), body[region.end :].strip()


def _same_rollup(existing: str, rendered: str) -> bool:
    """Equal but for the ``ingested_at`` stamp — no rewrite, no vault churn."""
    return _INGESTED_AT.sub("", existing) == _INGESTED_AT.sub("", rendered)


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
    cadence = (
        "Recurring calendar series." if not sample_block.all_day else "Recurring all-day event."
    )
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
