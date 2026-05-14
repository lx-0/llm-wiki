"""
Scan Thunderbird calendar data and produce a metadata overview.

Reads from the cached SQLite calendar database (Google Calendar sync).
Produces a structured timeline of events, attendees, and patterns.

Wired in two ways:
  - As a Registry-discovered Collector: `wiki collect calendar`. The
    `@register` decorator below adds `CalendarCollector` to the Registry;
    `flush.py` auto-spawns it as `collectors/cli.py calendar` when the
    piggyback fires.
  - As a direct CLI: `uv run python scripts/collectors/scan_calendar.py`
    still works and preserves the historical `--dry-run` / `--year` flags.
    (`--year` is CLI-only; the Collector path always does the full scan.)
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from core.config import RAW_DIR, ROOT_DIR, today_iso
from core.wiki_config import CONFIG

log = logging.getLogger(__name__)

_TB_PROFILE_RAW = CONFIG.personal.thunderbird_profile
THUNDERBIRD_PROFILE = (
    Path(_TB_PROFILE_RAW).expanduser() if _TB_PROFILE_RAW else Path()
)
CALENDAR_DB = THUNDERBIRD_PROFILE / "calendar-data" / "cache.sqlite"
LOCAL_DB = THUNDERBIRD_PROFILE / "calendar-data" / "local.sqlite"
REPORT_DIR = RAW_DIR / "notes" / "calendar"

def is_holiday(title: str) -> bool:
    """Match against `CONFIG.personal.calendar_skip_keywords` (locale-specific)."""
    if not title:
        return False
    keywords = CONFIG.personal.calendar_skip_keywords or []
    return any(kw.lower() in title.lower() for kw in keywords)


def categorize_event(title: str) -> str:
    """Bucket an event title using `CONFIG.personal.calendar_categories`.

    First match wins; falls back to the work-keyword bucket, then "Other".
    """
    title_lower = title.lower()
    for category, keywords in (CONFIG.personal.calendar_categories or {}).items():
        if any(kw.lower() in title_lower for kw in keywords):
            return category
    if any(kw.lower() in title_lower for kw in CONFIG.personal.calendar_work_keywords):
        return "Work / Workshops"
    return "Other"


def parse_attendee_ical(ical_str: str) -> str | None:
    """Extract name or email from iCal ATTENDEE/ORGANIZER string."""
    cn_match = re.search(r"CN=([^;:]+)", ical_str)
    if cn_match:
        name = cn_match.group(1).strip()
        if name and "calendar.google.com" not in name and name != "noreply@github.com":
            return name
    mailto_match = re.search(r"mailto:([^;\r\n]+)", ical_str)
    if mailto_match:
        email = mailto_match.group(1).strip()
        if "calendar.google.com" not in email:
            return email
    return None


def scan_calendar(db_path: Path, year_filter: int | None = None) -> dict:
    """Scan calendar SQLite and return structured data."""
    tmp_path = Path("/tmp/tb-cal-scan.sqlite")
    shutil.copy2(db_path, tmp_path)

    db = sqlite3.connect(str(tmp_path))
    cur = db.cursor()

    # Get all events
    cur.execute("SELECT title, event_start, event_end FROM cal_events ORDER BY event_start ASC")
    rows = cur.fetchall()

    events_by_year: dict[int, list] = {}
    categories = Counter()
    all_years = Counter()

    for title, start, end in rows:
        if not start or not title:
            continue
        try:
            ts = int(start) / 1_000_000
            dt = datetime.fromtimestamp(ts)
        except Exception:
            continue

        if is_holiday(title):
            continue

        year = dt.year
        if year > 2026:  # skip recurring holidays projected into future
            continue
        if year_filter and year != year_filter:
            continue

        all_years[year] += 1
        events_by_year.setdefault(year, []).append({
            "date": dt.strftime("%Y-%m-%d %H:%M"),
            "title": title,
        })

        categories[categorize_event(title)] += 1

    # Attendees
    attendees = Counter()
    try:
        cur.execute("SELECT icalString FROM cal_attendees")
        for (ical_str,) in cur.fetchall():
            name = parse_attendee_ical(ical_str)
            if name:
                attendees[name] += 1
    except Exception:
        pass

    db.close()
    tmp_path.unlink(missing_ok=True)

    return {
        "total_events": sum(all_years.values()),
        "years": dict(sorted(all_years.items())),
        "events_by_year": events_by_year,
        "categories": dict(categories.most_common()),
        "attendees": dict(attendees.most_common(20)),
    }


_REPORT_LABELS = {
    "en": {
        "title": "Thunderbird Calendar Overview",
        "summary": "events scanned (holidays filtered).",
        "scan_date": "Scan date",
        "events_per_year": "Events per year",
        "categories": "Categories",
        "top_attendees": "Top attendees",
        "events_count_suffix": "events",
    },
    "de": {
        "title": "Thunderbird Calendar Overview",
        "summary": "Events gescannt (Feiertage gefiltert).",
        "scan_date": "Scan vom",
        "events_per_year": "Events pro Jahr",
        "categories": "Kategorien",
        "top_attendees": "Top Teilnehmer",
        "events_count_suffix": "Events",
    },
}


def generate_report(data: dict) -> str:
    """Generate markdown report from calendar scan.

    Output language follows `CONFIG.personal.calendar_report_language` ("en" by
    default, "de" for the legacy format).
    """
    lang = (CONFIG.personal.calendar_report_language or "en").lower()
    if lang not in _REPORT_LABELS:
        lang = "en"
    L = _REPORT_LABELS[lang]

    lines = [
        "---",
        "type: calendar-scan",
        f"date: {today_iso()}",
        'origin: "thunderbird-calendar-scan"',
        "tags: [calendar, thunderbird, metadata, overview]",
        f"language: {lang}",
        "---",
        "",
        f"# {L['title']}",
        "",
        f"> {data['total_events']} {L['summary']} {L['scan_date']} {today_iso()}.",
        "",
        f"## {L['events_per_year']}",
        "",
    ]

    for year, count in sorted(data["years"].items()):
        lines.append(f"- **{year}:** {count} {L['events_count_suffix']}")

    lines.append("")
    lines.append(f"## {L['categories']}")
    lines.append("")
    for cat, count in data["categories"].items():
        lines.append(f"- **{cat}:** {count}")

    lines.append("")
    lines.append(f"## {L['top_attendees']}")
    lines.append("")
    for name, count in data["attendees"].items():
        lines.append(f"- {name} ({count})")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Events by year (most recent first)
    for year in sorted(data["events_by_year"].keys(), reverse=True):
        events = data["events_by_year"][year]
        lines.append(f"## {year} ({len(events)} {L['events_count_suffix']})")
        lines.append("")
        for ev in events:
            lines.append(f"- {ev['date']} | {ev['title']}")
        lines.append("")

    return "\n".join(lines)


# ── Collector wrapper ───────────────────────────────────────────────


@register
class CalendarCollector:
    """Thunderbird calendar SQLite scanner — Collector Protocol wrapper.

    Wraps scan_calendar + generate_report in the Registry-aware shape so
    `wiki collect calendar` works alongside email / jamie / tabs. Single-
    source substrate (one Thunderbird profile); the historical `--year`
    filter is CLI-only — the Collector path always does the full scan.
    """

    SPEC = CollectorSpec(
        name="calendar",
        output_subfolder="raw/notes/calendar",
        piggyback_default=False,  # operator-invoked; calendar shifts slowly
        piggyback_cooldown_hours=24,
        supports_incremental=False,  # full snapshot each time; no delta concept
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        """True iff CONFIG.personal.thunderbird_profile resolves to a calendar DB."""
        return bool(_TB_PROFILE_RAW) and CALENDAR_DB.exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self.is_configured():
            return RunResult(message="Thunderbird profile not configured or calendar DB missing")

        data = scan_calendar(CALENDAR_DB)
        if dry_run:
            return RunResult(
                files_skipped=1,
                message=f"[dry-run] would scan {data['total_events']} events across {len(data['years'])} year(s)",
            )

        report = generate_report(data)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"calendar-overview-{today_iso()}.md"
        report_path.write_text(report, encoding="utf-8")
        return RunResult(
            files_written=(report_path,),
            message=f"{data['total_events']} events across {len(data['years'])} year(s) → {report_path.name}",
        )


# ── Direct CLI entry (backward-compat) ──────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Scan Thunderbird calendar")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats")
    parser.add_argument("--year", type=int, help="Only scan one year")
    args = parser.parse_args()

    if not CALENDAR_DB.exists():
        print(f"Calendar DB not found: {CALENDAR_DB}")
        return

    print(f"Scanning {CALENDAR_DB}...")
    data = scan_calendar(CALENDAR_DB, year_filter=args.year)

    print(f"Total events (non-holiday): {data['total_events']}")
    print(f"Years: {data['years']}")
    print(f"Categories: {data['categories']}")
    print(f"Top attendees: {list(data['attendees'].keys())[:5]}")

    if args.dry_run:
        return

    report = generate_report(data)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"calendar-overview-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path.relative_to(ROOT_DIR)}")
    print("Run 'uv run python scripts/compile.py' to compile into wiki articles.")


if __name__ == "__main__":
    main()
