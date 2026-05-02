"""
Scan all browser data: Firefox Tab Groups, Bookmarks, History + Chrome Bookmarks, History.

Produces a comprehensive overview of browsing patterns, research interests,
and saved resources.

Usage:
    uv run python scripts/scan-browser.py                   # full scan, save report
    uv run python scripts/scan-browser.py --dry-run         # just show stats
    uv run python scripts/scan-browser.py --source firefox  # only Firefox
    uv run python scripts/scan-browser.py --source chrome   # only Chrome
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from config import RAW_DIR, ROOT_DIR, today_iso
from wiki_config import CONFIG

# Paths — populated from CONFIG.personal so the engine has no hardcoded
# personal profile IDs / backup folders. Empty CONFIG values mean the
# corresponding scanner half is a no-op.
_FF_PROFILE_RAW = CONFIG.personal.firefox_profile
FF_PROFILE = Path(_FF_PROFILE_RAW).expanduser() if _FF_PROFILE_RAW else Path()
FF_PLACES = FF_PROFILE / "places.sqlite" if _FF_PROFILE_RAW else Path()

_STG_RAW = CONFIG.personal.stg_backup_dir
STG_BACKUP_DIR = Path(_STG_RAW).expanduser() if _STG_RAW else Path()

CHROME_PROFILE = Path.home() / "Library/Application Support/Google/Chrome/Default"
CHROME_BOOKMARKS = CHROME_PROFILE / "Bookmarks"
CHROME_HISTORY = CHROME_PROFILE / "History"

REPORT_DIR = RAW_DIR / "notes" / "browser"

SKIP_DOMAINS = {
    "localhost", "127.0.0.1", "about:blank", "", "newtab",
    "accounts.google.com", "mail.google.com",
}


def clean_domain(url: str) -> str | None:
    """Extract and clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        if domain in SKIP_DOMAINS or not domain:
            return None
        return domain
    except Exception:
        return None


# ── Firefox Tab Groups ────────────────────────────────────────────────

def scan_stg(backup_dir: Path) -> dict | None:
    """Scan Simple Tab Groups backup."""
    if not backup_dir.exists():
        return None
    files = sorted(backup_dir.glob("*.json"))
    if not files:
        return None

    data = json.loads(files[-1].read_text(encoding="utf-8"))
    groups = []
    total_tabs = 0

    for group in data.get("groups", []):
        title = group.get("title", "(untitled)")
        tabs = group.get("tabs", [])
        total_tabs += len(tabs)
        tab_list = []
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            tab_list.append({
                "title": tab.get("title", ""),
                "url": tab.get("url", ""),
            })
        if tabs:
            groups.append({"title": title, "tab_count": len(tabs), "tabs": tab_list})

    groups.sort(key=lambda x: x["tab_count"], reverse=True)
    return {"total_groups": len(groups), "total_tabs": total_tabs, "groups": groups}


# ── Firefox Bookmarks + History ───────────────────────────────────────

def scan_firefox_places(places_path: Path) -> dict | None:
    """Scan Firefox places.sqlite for bookmarks and history."""
    if not places_path.exists():
        return None

    tmp = Path("/tmp/ff-places-scan.sqlite")
    shutil.copy2(places_path, tmp)
    db = sqlite3.connect(str(tmp))
    cur = db.cursor()

    # Bookmarks
    bookmarks = []
    cur.execute("""
        SELECT b.title, p.url, b.dateAdded, parent.title as folder
        FROM moz_bookmarks b
        JOIN moz_places p ON b.fk = p.id
        LEFT JOIN moz_bookmarks parent ON b.parent = parent.id
        WHERE b.type = 1 AND p.url NOT LIKE 'place:%'
        ORDER BY b.dateAdded DESC
    """)
    for title, url, date_added, folder in cur.fetchall():
        domain = clean_domain(url)
        if not domain:
            continue
        dt = None
        if date_added:
            try:
                dt = datetime.fromtimestamp(date_added / 1_000_000).strftime("%Y-%m-%d")
            except Exception:
                pass
        bookmarks.append({
            "title": title or "(no title)",
            "url": url,
            "domain": domain,
            "date": dt,
            "folder": folder or "",
        })

    # History - top visited
    history_domains = Counter()
    cur.execute("""
        SELECT url, title, visit_count, last_visit_date
        FROM moz_places
        WHERE visit_count > 0
        ORDER BY visit_count DESC
    """)
    history_entries = []
    for url, title, visit_count, last_visit in cur.fetchall():
        domain = clean_domain(url)
        if not domain:
            continue
        history_domains[domain] += visit_count
        if visit_count >= 3:
            dt = None
            if last_visit:
                try:
                    dt = datetime.fromtimestamp(last_visit / 1_000_000).strftime("%Y-%m-%d")
                except Exception:
                    pass
            history_entries.append({
                "title": title or "(no title)",
                "url": url,
                "visits": visit_count,
                "last_visit": dt,
                "domain": domain,
            })

    # History date range
    cur.execute("SELECT MIN(visit_date), MAX(visit_date) FROM moz_historyvisits")
    mn, mx = cur.fetchone()
    date_range = None
    if mn and mx:
        try:
            date_range = {
                "from": datetime.fromtimestamp(mn / 1_000_000).strftime("%Y-%m-%d"),
                "to": datetime.fromtimestamp(mx / 1_000_000).strftime("%Y-%m-%d"),
            }
        except Exception:
            pass

    cur.execute("SELECT COUNT(*) FROM moz_historyvisits")
    total_visits = cur.fetchone()[0]

    db.close()
    tmp.unlink(missing_ok=True)

    # Bookmark folders
    bm_folders = Counter()
    for bm in bookmarks:
        bm_folders[bm["folder"]] += 1

    # Search history from formhistory.sqlite
    searches = []
    form_history = places_path.parent / "formhistory.sqlite"
    if form_history.exists():
        tmp_fh = Path("/tmp/ff-formhistory-scan.sqlite")
        shutil.copy2(form_history, tmp_fh)
        try:
            fh_db = sqlite3.connect(str(tmp_fh))
            fh_cur = fh_db.cursor()
            fh_cur.execute("""
                SELECT value, timesUsed, lastUsed FROM moz_formhistory
                WHERE fieldname = 'searchbar-history'
                ORDER BY lastUsed DESC
            """)
            for value, times, last_used in fh_cur.fetchall():
                dt = None
                if last_used:
                    try:
                        dt = datetime.fromtimestamp(last_used / 1_000_000).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                searches.append({"query": value, "times": times, "last_used": dt})
            fh_db.close()
        except Exception:
            pass
        tmp_fh.unlink(missing_ok=True)

    # Google searches from URL history
    google_searches = []
    import urllib.parse
    for entry in history_entries:
        if "google." in entry.get("domain", "") and "/search" in entry.get("url", ""):
            try:
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(entry["url"]).query)
                q = parsed_qs.get("q", [""])[0]
                if q:
                    google_searches.append({
                        "query": q,
                        "visits": entry["visits"],
                        "last_visit": entry["last_visit"],
                    })
            except Exception:
                pass

    return {
        "bookmarks": bookmarks,
        "bookmark_count": len(bookmarks),
        "bookmark_folders": dict(bm_folders.most_common(20)),
        "history_top": history_entries[:50],
        "history_domains": dict(history_domains.most_common(30)),
        "history_total_entries": len(history_entries),
        "history_total_visits": total_visits,
        "history_date_range": date_range,
        "searches": searches,
        "google_searches": google_searches[:30],
    }


# ── Chrome Bookmarks + History ────────────────────────────────────────

def walk_chrome_bookmarks(node: dict, path: str = "") -> list[dict]:
    """Recursively extract Chrome bookmarks."""
    items = []
    name = node.get("name", "")
    current = f"{path}/{name}" if path else name

    if node.get("type") == "url":
        url = node.get("url", "")
        domain = clean_domain(url)
        if domain:
            date_added = node.get("date_added")
            dt = None
            if date_added:
                try:
                    # Chrome uses Windows epoch (microseconds since 1601-01-01)
                    ts = (int(date_added) - 11644473600000000) / 1_000_000
                    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                except Exception:
                    pass
            items.append({
                "title": name,
                "url": url,
                "domain": domain,
                "date": dt,
                "folder": path,
            })

    for child in node.get("children", []):
        items.extend(walk_chrome_bookmarks(child, current))
    return items


def scan_chrome_bookmarks(bm_path: Path) -> list[dict] | None:
    """Scan Chrome bookmarks."""
    if not bm_path.exists():
        return None
    data = json.loads(bm_path.read_text(encoding="utf-8"))
    bookmarks = []
    for root_key in ["bookmark_bar", "other", "synced"]:
        if root_key in data.get("roots", {}):
            bookmarks.extend(walk_chrome_bookmarks(data["roots"][root_key]))
    return bookmarks


def scan_chrome_history(history_path: Path) -> dict | None:
    """Scan Chrome history."""
    if not history_path.exists():
        return None

    tmp = Path("/tmp/chrome-history-scan.sqlite")
    shutil.copy2(history_path, tmp)

    try:
        db = sqlite3.connect(str(tmp))
        cur = db.cursor()

        domains = Counter()
        entries = []
        cur.execute("""
            SELECT url, title, visit_count, last_visit_time
            FROM urls
            WHERE visit_count > 0
            ORDER BY visit_count DESC
        """)
        for url, title, visit_count, last_visit in cur.fetchall():
            domain = clean_domain(url)
            if not domain:
                continue
            domains[domain] += visit_count
            if visit_count >= 3:
                dt = None
                if last_visit:
                    try:
                        ts = (last_visit - 11644473600000000) / 1_000_000
                        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                entries.append({
                    "title": title or "(no title)",
                    "url": url,
                    "visits": visit_count,
                    "last_visit": dt,
                    "domain": domain,
                })

        cur.execute("SELECT COUNT(*) FROM visits")
        total_visits = cur.fetchone()[0]

        db.close()
    except Exception as e:
        return {"error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)

    return {
        "top_entries": entries[:50],
        "domains": dict(domains.most_common(30)),
        "total_visits": total_visits,
    }


# ── Report Generation ─────────────────────────────────────────────────

def generate_report(ff_stg: dict | None, ff_places: dict | None,
                    chrome_bm: list | None, chrome_hist: dict | None) -> str:
    """Generate comprehensive browser overview report."""
    lines = [
        "---",
        "type: browser-scan",
        f"date: {today_iso()}",
        'origin: "firefox+chrome-local-scan"',
        "tags: [browser, tabs, bookmarks, history, firefox, chrome, overview]",
        "language: de",
        "---",
        "",
        "# Browser Overview — Firefox + Chrome",
        "",
        f"> Scan vom {today_iso()}. Alle Daten lokal gelesen.",
        "",
    ]

    # ── STG ──
    if ff_stg:
        lines.append(f"## Firefox Tab Groups ({ff_stg['total_tabs']} tabs in {ff_stg['total_groups']} groups)")
        lines.append("")
        for g in ff_stg["groups"]:
            if g["tab_count"] == 0:
                continue
            lines.append(f"### {g['title']} ({g['tab_count']} tabs)")
            lines.append("")
            for tab in g["tabs"][:10]:
                lines.append(f"- {tab['title'][:80]}")
                if tab["url"]:
                    lines.append(f"  {tab['url'][:100]}")
            if g["tab_count"] > 10:
                lines.append(f"- ... +{g['tab_count'] - 10} weitere tabs")
            lines.append("")

    # ── Firefox Bookmarks ──
    if ff_places:
        lines.append(f"## Firefox Bookmarks ({ff_places['bookmark_count']})")
        lines.append("")
        if ff_places["bookmark_folders"]:
            lines.append("### Ordner")
            lines.append("")
            for folder, count in ff_places["bookmark_folders"].items():
                lines.append(f"- {folder}: {count}")
            lines.append("")
        lines.append("### Neueste 30 Bookmarks")
        lines.append("")
        for bm in ff_places["bookmarks"][:30]:
            lines.append(f"- [{bm['title'][:60]}]({bm['url'][:100]}) ({bm['date']}, {bm['folder']})")
        lines.append("")

        # ── Firefox History ──
        dr = ff_places.get("history_date_range", {})
        lines.append(f"## Firefox History ({ff_places['history_total_visits']} visits, {dr.get('from','?')}—{dr.get('to','?')})")
        lines.append("")
        lines.append("### Top Domains")
        lines.append("")
        for domain, count in list(ff_places["history_domains"].items())[:20]:
            lines.append(f"- {domain}: {count} visits")
        lines.append("")
        lines.append("### Meistbesuchte Seiten")
        lines.append("")
        for entry in ff_places["history_top"][:30]:
            lines.append(f"- {entry['title'][:60]} ({entry['visits']}x, zuletzt {entry['last_visit']})")
            lines.append(f"  {entry['url'][:100]}")
        lines.append("")

    # ── Firefox Search History ──
    if ff_places:
        searches = ff_places.get("searches", [])
        google = ff_places.get("google_searches", [])
        if searches or google:
            lines.append(f"## Firefox Suchverlauf")
            lines.append("")
            if searches:
                lines.append("### Suchleiste")
                lines.append("")
                for s in searches[:30]:
                    lines.append(f"- \"{s['query']}\" ({s['times']}x, zuletzt {s['last_used']})")
                lines.append("")
            if google:
                lines.append("### Google Suchen (aus URL History)")
                lines.append("")
                for s in google[:30]:
                    lines.append(f"- \"{s['query']}\" ({s['visits']}x, zuletzt {s['last_visit']})")
                lines.append("")

    # ── Chrome Bookmarks ──
    if chrome_bm:
        lines.append(f"## Chrome Bookmarks ({len(chrome_bm)})")
        lines.append("")
        for bm in chrome_bm[:20]:
            lines.append(f"- {bm['title'][:60]} ({bm['domain']})")
        lines.append("")

    # ── Chrome History ──
    if chrome_hist and not chrome_hist.get("error"):
        lines.append(f"## Chrome History ({chrome_hist['total_visits']} visits)")
        lines.append("")
        lines.append("### Top Domains")
        lines.append("")
        for domain, count in list(chrome_hist["domains"].items())[:20]:
            lines.append(f"- {domain}: {count} visits")
        lines.append("")
        lines.append("### Meistbesuchte Seiten")
        lines.append("")
        for entry in chrome_hist["top_entries"][:20]:
            lines.append(f"- {entry['title'][:60]} ({entry['visits']}x)")
        lines.append("")
    elif chrome_hist and chrome_hist.get("error"):
        lines.append(f"## Chrome History — Error: {chrome_hist['error']}")
        lines.append("(Chrome muss geschlossen sein um die History DB zu lesen)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Scan Firefox + Chrome browser data")
    parser.add_argument("--dry-run", action="store_true", help="Only show stats")
    parser.add_argument("--source", choices=["firefox", "chrome", "all"], default="all")
    args = parser.parse_args()

    ff_stg = None
    ff_places = None
    chrome_bm = None
    chrome_hist = None

    if args.source in ("firefox", "all"):
        print("Scanning Firefox Tab Groups...")
        ff_stg = scan_stg(STG_BACKUP_DIR)
        if ff_stg:
            print(f"  {ff_stg['total_tabs']} tabs in {ff_stg['total_groups']} groups")
        else:
            print("  No STG backup found")

        print("Scanning Firefox Bookmarks + History...")
        ff_places = scan_firefox_places(FF_PLACES)
        if ff_places:
            print(f"  {ff_places['bookmark_count']} bookmarks, {ff_places['history_total_visits']} visits")
        else:
            print("  places.sqlite not found")

    if args.source in ("chrome", "all"):
        print("Scanning Chrome Bookmarks...")
        chrome_bm = scan_chrome_bookmarks(CHROME_BOOKMARKS)
        if chrome_bm:
            print(f"  {len(chrome_bm)} bookmarks")
        else:
            print("  No Chrome bookmarks found")

        print("Scanning Chrome History...")
        chrome_hist = scan_chrome_history(CHROME_HISTORY)
        if chrome_hist and not chrome_hist.get("error"):
            print(f"  {chrome_hist['total_visits']} visits")
        elif chrome_hist:
            print(f"  Error: {chrome_hist['error']}")
        else:
            print("  No Chrome history found")

    if args.dry_run:
        return

    report = generate_report(ff_stg, ff_places, chrome_bm, chrome_hist)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"browser-overview-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path.relative_to(ROOT_DIR)}")
    print("Run 'uv run python scripts/compile.py' to compile into wiki articles.")


if __name__ == "__main__":
    main()
