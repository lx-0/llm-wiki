"""Tests for `collectors/scan_browser.py:BrowserCollector` — Protocol + multi-source scan."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _seed_firefox_places(db_path: Path) -> None:
    """Minimal Firefox places.sqlite — one bookmark, one visited page."""
    db = sqlite3.connect(str(db_path))
    cur = db.cursor()
    cur.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, last_visit_date INTEGER)")
    cur.execute("CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, fk INTEGER, type INTEGER, title TEXT, parent INTEGER, dateAdded INTEGER)")
    cur.execute("CREATE TABLE moz_historyvisits (id INTEGER PRIMARY KEY, visit_date INTEGER)")
    cur.execute("INSERT INTO moz_places VALUES (1, 'https://example.com/page', 'Example', 5, 1700000000000000)")
    cur.execute("INSERT INTO moz_bookmarks VALUES (10, 1, 1, 'Example bookmark', 2, 1700000000000000)")
    cur.execute("INSERT INTO moz_bookmarks VALUES (2, NULL, 2, 'Toolbar', NULL, NULL)")
    cur.execute("INSERT INTO moz_historyvisits VALUES (1, 1700000000000000)")
    db.commit()
    db.close()


def _seed_chrome_history(db_path: Path) -> None:
    """Minimal Chrome history SQLite — urls + visits tables."""
    db = sqlite3.connect(str(db_path))
    cur = db.cursor()
    cur.execute("CREATE TABLE urls (url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER)")
    cur.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY)")
    cur.execute("INSERT INTO urls VALUES ('https://chrome-site.com', 'Chrome Page', 8, 13350000000000000)")
    cur.execute("INSERT INTO visits VALUES (1)")
    db.commit()
    db.close()


def test_browser_collector_registered():
    from collectors import get_collector

    c = get_collector("browser")
    assert c is not None
    assert c.SPEC.name == "browser"
    assert c.SPEC.output_subfolder == "raw/notes/browser"
    assert c.SPEC.piggyback_default is False
    assert c.SPEC.supports_incremental is False


def test_browser_is_configured_false_when_no_sources(monkeypatch):
    from collectors import scan_browser

    monkeypatch.setattr(scan_browser, "_FF_PROFILE_RAW", "")
    monkeypatch.setattr(scan_browser, "_STG_RAW", "")
    monkeypatch.setattr(scan_browser, "FF_PLACES", Path("/nonexistent/places.sqlite"))
    monkeypatch.setattr(scan_browser, "STG_BACKUP_DIR", Path("/nonexistent/stg"))
    monkeypatch.setattr(scan_browser, "CHROME_BOOKMARKS", Path("/nonexistent/Bookmarks"))
    monkeypatch.setattr(scan_browser, "CHROME_HISTORY", Path("/nonexistent/History"))

    assert scan_browser.BrowserCollector().is_configured() is False


def test_browser_is_configured_true_when_one_source(monkeypatch, tmp_path):
    from collectors import scan_browser

    chrome_bm = tmp_path / "Bookmarks"
    chrome_bm.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scan_browser, "_FF_PROFILE_RAW", "")
    monkeypatch.setattr(scan_browser, "_STG_RAW", "")
    monkeypatch.setattr(scan_browser, "FF_PLACES", Path("/nonexistent/places.sqlite"))
    monkeypatch.setattr(scan_browser, "STG_BACKUP_DIR", Path("/nonexistent/stg"))
    monkeypatch.setattr(scan_browser, "CHROME_BOOKMARKS", chrome_bm)
    monkeypatch.setattr(scan_browser, "CHROME_HISTORY", Path("/nonexistent/History"))

    assert scan_browser.BrowserCollector().is_configured() is True


def test_browser_run_skips_when_not_configured(monkeypatch):
    from collectors import scan_browser

    monkeypatch.setattr(scan_browser, "_FF_PROFILE_RAW", "")
    monkeypatch.setattr(scan_browser, "_STG_RAW", "")
    monkeypatch.setattr(scan_browser, "FF_PLACES", Path("/nonexistent/places.sqlite"))
    monkeypatch.setattr(scan_browser, "STG_BACKUP_DIR", Path("/nonexistent/stg"))
    monkeypatch.setattr(scan_browser, "CHROME_BOOKMARKS", Path("/nonexistent/Bookmarks"))
    monkeypatch.setattr(scan_browser, "CHROME_HISTORY", Path("/nonexistent/History"))

    result = scan_browser.BrowserCollector().run()
    assert result.files_written == ()
    assert "No browser sources configured" in result.message


def test_browser_run_dry_run_does_not_write(monkeypatch, tmp_path):
    from collectors import scan_browser

    chrome_bm = tmp_path / "Bookmarks"
    chrome_bm.write_text(json.dumps({
        "roots": {"bookmark_bar": {"name": "Bar", "children": [
            {"type": "url", "name": "Site", "url": "https://site.com", "date_added": "13350000000000000"}
        ]}}
    }), encoding="utf-8")

    monkeypatch.setattr(scan_browser, "_FF_PROFILE_RAW", "")
    monkeypatch.setattr(scan_browser, "_STG_RAW", "")
    monkeypatch.setattr(scan_browser, "FF_PLACES", Path("/nonexistent/places.sqlite"))
    monkeypatch.setattr(scan_browser, "STG_BACKUP_DIR", Path("/nonexistent/stg"))
    monkeypatch.setattr(scan_browser, "CHROME_BOOKMARKS", chrome_bm)
    monkeypatch.setattr(scan_browser, "CHROME_HISTORY", Path("/nonexistent/History"))
    monkeypatch.setattr(scan_browser, "REPORT_DIR", tmp_path / "reports")

    result = scan_browser.BrowserCollector().run(dry_run=True)
    assert result.files_written == ()
    assert result.files_skipped == 1
    assert "[dry-run]" in result.message
    assert "chrome_bm" in result.message
    assert not (tmp_path / "reports").exists()


def test_browser_run_writes_report_multi_source(monkeypatch, tmp_path):
    from collectors import scan_browser

    # Firefox places
    ff_places = tmp_path / "places.sqlite"
    _seed_firefox_places(ff_places)
    # Chrome history
    chrome_hist = tmp_path / "History"
    _seed_chrome_history(chrome_hist)
    # Chrome bookmarks
    chrome_bm = tmp_path / "Bookmarks"
    chrome_bm.write_text(json.dumps({
        "roots": {"bookmark_bar": {"name": "Bar", "children": [
            {"type": "url", "name": "ChromeSite", "url": "https://chrome-bm.com", "date_added": "13350000000000000"}
        ]}}
    }), encoding="utf-8")

    monkeypatch.setattr(scan_browser, "_FF_PROFILE_RAW", str(tmp_path))
    monkeypatch.setattr(scan_browser, "_STG_RAW", "")
    monkeypatch.setattr(scan_browser, "FF_PLACES", ff_places)
    monkeypatch.setattr(scan_browser, "STG_BACKUP_DIR", Path("/nonexistent/stg"))
    monkeypatch.setattr(scan_browser, "CHROME_BOOKMARKS", chrome_bm)
    monkeypatch.setattr(scan_browser, "CHROME_HISTORY", chrome_hist)
    monkeypatch.setattr(scan_browser, "REPORT_DIR", tmp_path / "reports")

    result = scan_browser.BrowserCollector().run()
    assert len(result.files_written) == 1
    content = result.files_written[0].read_text(encoding="utf-8")
    assert "type: browser-scan" in content
    assert "Firefox Bookmarks" in content
    assert "Chrome History" in content
    # 3 of 4 sources present (ff_places, chrome_bm, chrome_hist; STG absent)
    assert "3 source(s) scanned" in result.message


def test_scan_stg_no_op_for_empty_path():
    """Empty config → Path() == cwd, which `.exists()` would call truthy. Guard works."""
    from collectors import scan_browser

    assert scan_browser.scan_stg(Path()) is None


def test_scan_firefox_places_no_op_for_directory():
    """`.exists()` is True for a dir; `.is_file()` guard makes it a clean no-op."""
    from collectors import scan_browser

    assert scan_browser.scan_firefox_places(Path()) is None


def test_clean_domain_filters_skip_list():
    from collectors import scan_browser

    assert scan_browser.clean_domain("https://www.example.com/page") == "example.com"
    assert scan_browser.clean_domain("https://localhost/x") is None
    assert scan_browser.clean_domain("https://mail.google.com/x") is None
    assert scan_browser.clean_domain("not a url") is None
