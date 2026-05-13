"""Tests for `collectors/scan_tabs.py:TabsCollector` — Protocol conformance + Registry."""

from __future__ import annotations

import json
from pathlib import Path


def test_tabs_collector_registered():
    """Importing collectors triggers @register; TabsCollector should be discoverable."""
    from collectors import get_collector

    c = get_collector("tabs")
    assert c is not None
    assert c.SPEC.name == "tabs"
    assert c.SPEC.output_subfolder == "raw/notes/browser"
    assert c.SPEC.piggyback_default is False
    assert c.SPEC.supports_incremental is False
    assert c.SPEC.supports_account_loop is False


def test_tabs_is_configured_false_when_no_backup_dir(monkeypatch, tmp_path):
    from collectors import scan_tabs

    monkeypatch.setattr(scan_tabs, "_STG_RAW", "")
    monkeypatch.setattr(scan_tabs, "DEFAULT_BACKUP_DIR", Path(""))

    assert scan_tabs.TabsCollector().is_configured() is False


def test_tabs_run_skips_when_not_configured(monkeypatch):
    from collectors import scan_tabs

    monkeypatch.setattr(scan_tabs, "_STG_RAW", "")
    monkeypatch.setattr(scan_tabs, "DEFAULT_BACKUP_DIR", Path(""))

    result = scan_tabs.TabsCollector().run()
    assert result.files_written == ()
    assert "not configured" in result.message


def test_tabs_run_dry_run_does_not_write(monkeypatch, tmp_path):
    from collectors import scan_tabs

    # Seed a backup file
    backup_dir = tmp_path / "stg"
    backup_dir.mkdir()
    backup_path = backup_dir / "stg-2026-05-13.json"
    backup_path.write_text(json.dumps({
        "version": 5,
        "groups": [{"title": "Work", "tabs": [{"url": "https://example.com", "title": "Ex"}]}],
    }), encoding="utf-8")

    monkeypatch.setattr(scan_tabs, "_STG_RAW", str(backup_dir))
    monkeypatch.setattr(scan_tabs, "DEFAULT_BACKUP_DIR", backup_dir)
    monkeypatch.setattr(scan_tabs, "REPORT_DIR", tmp_path / "reports")

    result = scan_tabs.TabsCollector().run(dry_run=True)
    assert result.files_written == ()
    assert result.files_skipped == 1
    assert "[dry-run]" in result.message
    # No report written in dry-run
    assert not (tmp_path / "reports").exists()


def test_tabs_run_writes_report(monkeypatch, tmp_path):
    from collectors import scan_tabs

    backup_dir = tmp_path / "stg"
    backup_dir.mkdir()
    backup_path = backup_dir / "stg-2026-05-13.json"
    backup_path.write_text(json.dumps({
        "version": 5,
        "groups": [
            {"title": "Work", "tabs": [{"url": "https://a.com", "title": "A"},
                                       {"url": "https://b.com", "title": "B"}]},
            {"title": "Reading", "tabs": [{"url": "https://c.com", "title": "C"}]},
        ],
    }), encoding="utf-8")

    monkeypatch.setattr(scan_tabs, "_STG_RAW", str(backup_dir))
    monkeypatch.setattr(scan_tabs, "DEFAULT_BACKUP_DIR", backup_dir)
    monkeypatch.setattr(scan_tabs, "REPORT_DIR", tmp_path / "reports")

    result = scan_tabs.TabsCollector().run()
    assert len(result.files_written) == 1
    out = result.files_written[0]
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Firefox Tab Groups Overview" in content
    assert "3 Tabs in 2 Gruppen" in content
    assert "## Work (2 tabs)" in content


def test_tabs_run_no_backup_found(monkeypatch, tmp_path):
    from collectors import scan_tabs

    empty_dir = tmp_path / "stg-empty"
    empty_dir.mkdir()

    monkeypatch.setattr(scan_tabs, "_STG_RAW", str(empty_dir))
    monkeypatch.setattr(scan_tabs, "DEFAULT_BACKUP_DIR", empty_dir)

    result = scan_tabs.TabsCollector().run()
    assert result.files_written == ()
    assert "No STG backup found" in result.message


def test_register_is_idempotent_for_same_class():
    """Double-import (__main__ + collectors.<name>) must not raise."""
    from collectors.base import register
    from collectors import scan_tabs

    # Re-applying @register to the same class should be a no-op, not raise.
    cls = register(scan_tabs.TabsCollector)
    assert cls is scan_tabs.TabsCollector


def test_register_rejects_genuine_name_collision():
    """Different class trying to claim a registered name must still raise."""
    import pytest
    from collectors.base import CollectorSpec, RunResult, register

    class FakeTabs:
        SPEC = CollectorSpec(name="tabs", output_subfolder="raw/x", piggyback_default=False)
        def is_configured(self): return False
        def run(self, *, dry_run=False, incremental=False): return RunResult()

    with pytest.raises(ValueError, match="already registered"):
        register(FakeTabs)
