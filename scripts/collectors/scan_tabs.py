"""
Scan Firefox Simple Tab Groups backups and produce a metadata overview.

Reads STG backup JSON files and extracts tab groups, URLs, and titles.
Produces a structured overview of research interests, projects, and browsing patterns.

Wired in two ways:
  - As a Registry-discovered Collector: `wiki collect tabs`. The `@register`
    decorator below adds `TabsCollector` to `collectors.Registry`; `flush.py`
    auto-spawns it as `collectors/cli.py tabs` when piggyback fires.
  - As a direct CLI: `uv run python scripts/collectors/scan-tabs.py` still works
    and preserves the historical `--dry-run` / `--backup-dir` flags.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from core.config import RAW_DIR, ROOT_DIR, today_iso
from core.wiki_config import CONFIG

log = logging.getLogger(__name__)

_STG_RAW = CONFIG.personal.stg_backup_dir
DEFAULT_BACKUP_DIR = Path(_STG_RAW).expanduser() if _STG_RAW else Path()
REPORT_DIR = RAW_DIR / "notes" / "browser"


def find_newest_backup(backup_dir: Path) -> Path | None:
    """Find the most recent STG backup file."""
    if not backup_dir.exists():
        return None
    files = sorted(backup_dir.glob("*.json"))
    return files[-1] if files else None


def scan_backup(backup_path: Path) -> dict:
    """Parse STG backup and extract structured data."""
    data = json.loads(backup_path.read_text(encoding="utf-8"))

    groups_data = []
    total_tabs = 0
    all_domains = Counter()

    for group in data.get("groups", []):
        title = group.get("title", "(untitled)")
        tabs = group.get("tabs", [])
        total_tabs += len(tabs)

        tab_list = []
        domains = Counter()

        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            url = tab.get("url", "")
            tab_title = tab.get("title", "")

            # Extract domain
            try:
                domain = urlparse(url).netloc
                if domain:
                    # Simplify domain
                    domain = domain.replace("www.", "")
                    domains[domain] += 1
                    all_domains[domain] += 1
            except Exception:
                pass

            tab_list.append({
                "title": tab_title,
                "url": url,
            })

        groups_data.append({
            "title": title,
            "tab_count": len(tabs),
            "tabs": tab_list,
            "top_domains": dict(domains.most_common(5)),
        })

    # Sort by tab count
    groups_data.sort(key=lambda x: x["tab_count"], reverse=True)

    return {
        "version": data.get("version", "?"),
        "total_groups": len(groups_data),
        "total_tabs": total_tabs,
        "groups": groups_data,
        "top_domains": dict(all_domains.most_common(30)),
    }


def generate_report(data: dict) -> str:
    """Generate markdown report from tab groups scan."""
    lines = [
        "---",
        "type: browser-scan",
        f"date: {today_iso()}",
        'origin: "firefox-simple-tab-groups"',
        "tags: [browser, tabs, firefox, research, overview]",
        "language: de",
        "---",
        "",
        "# Firefox Tab Groups Overview",
        "",
        f"> {data['total_tabs']} Tabs in {data['total_groups']} Gruppen. "
        f"STG Version {data['version']}. Scan vom {today_iso()}.",
        "",
        "## Top Domains",
        "",
    ]

    for domain, count in list(data["top_domains"].items())[:20]:
        lines.append(f"- {domain} ({count})")

    lines.append("")
    lines.append("---")
    lines.append("")

    for group in data["groups"]:
        if group["tab_count"] == 0:
            continue

        title = group["title"]
        count = group["tab_count"]
        lines.append(f"## {title} ({count} tabs)")
        lines.append("")

        # Top domains for this group
        if group["top_domains"]:
            domains_str = ", ".join(
                f"{d} ({c})" for d, c in list(group["top_domains"].items())[:3]
            )
            lines.append(f"Domains: {domains_str}")
            lines.append("")

        # List tabs
        for tab in group["tabs"]:
            tab_title = tab["title"][:80] if tab["title"] else "(no title)"
            url = tab["url"][:100] if tab["url"] else ""
            lines.append(f"- {tab_title}")
            if url:
                lines.append(f"  {url}")

        lines.append("")

    return "\n".join(lines)


# ── Collector wrapper ───────────────────────────────────────────────


@register
class TabsCollector:
    """Firefox Simple Tab Groups backup scanner — Collector Protocol wrapper.

    Wraps the existing scan_backup + generate_report functions in the
    Registry-aware shape so `wiki collect tabs` works alongside email
    and jamie. Single-source substrate; --backup-dir override flows via
    CONFIG.personal.stg_backup_dir, not a per-run flag.
    """

    SPEC = CollectorSpec(
        name="tabs",
        output_subfolder="raw/notes/browser",
        piggyback_default=False,  # operator-invoked; STG backups are sporadic
        piggyback_cooldown_hours=24,
        supports_incremental=False,  # full snapshot each time; no delta concept
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        """True iff CONFIG.personal.stg_backup_dir resolves to an existing dir."""
        return bool(_STG_RAW) and DEFAULT_BACKUP_DIR.exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self.is_configured():
            return RunResult(message="STG backup dir not configured or missing")

        backup_path = find_newest_backup(DEFAULT_BACKUP_DIR)
        if not backup_path:
            return RunResult(message=f"No STG backup found in {DEFAULT_BACKUP_DIR}")

        data = scan_backup(backup_path)
        if dry_run:
            return RunResult(
                files_skipped=1,
                message=f"[dry-run] would scan {data['total_tabs']} tabs in {data['total_groups']} groups",
            )

        report = generate_report(data)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"tab-groups-overview-{today_iso()}.md"
        report_path.write_text(report, encoding="utf-8")
        return RunResult(
            files_written=(report_path,),
            message=f"{data['total_tabs']} tabs in {data['total_groups']} groups → {report_path.name}",
        )


# ── Direct CLI entry (backward-compat) ──────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Scan Firefox Simple Tab Groups")
    parser.add_argument("--dry-run", action="store_true", help="Only show group stats")
    parser.add_argument("--backup-dir", type=str, help="Path to STG backup directory")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir) if args.backup_dir else DEFAULT_BACKUP_DIR
    backup_path = find_newest_backup(backup_dir)

    if not backup_path:
        print(f"No STG backup found in {backup_dir}")
        return

    print(f"Reading: {backup_path.name}")
    data = scan_backup(backup_path)
    print(f"Found: {data['total_tabs']} tabs in {data['total_groups']} groups")

    if args.dry_run:
        print()
        for g in data["groups"]:
            if g["tab_count"] > 0:
                print(f"  {g['tab_count']:>4} tabs | {g['title']}")
        return

    report = generate_report(data)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"tab-groups-overview-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path.relative_to(ROOT_DIR)}")
    print("Run 'uv run python scripts/compile.py' to compile into wiki articles.")


if __name__ == "__main__":
    main()
