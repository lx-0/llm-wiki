"""Tests for `collectors/scan_screenshots.py:ScreenshotsCollector`.

The scan path is vision-LLM-bound (gemma4 over Ollama), so the run()
tests monkeypatch `scan()` to a canned result dict and assert the
RunResult mapping. Pure helpers (timestamp parsing, RunResult bridging)
are tested directly.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def test_screenshots_collector_registered():
    from collectors import get_collector

    c = get_collector("screenshots")
    assert c is not None
    assert c.SPEC.name == "screenshots"
    assert c.SPEC.output_subfolder == "raw/notes/screenshots"
    # This is the one migrated collector that IS a piggyback (was in the
    # legacy hardcoded list).
    assert c.SPEC.piggyback_default is True
    assert c.SPEC.supports_incremental is False


def test_screenshots_is_piggyback_discovered():
    """piggyback_collectors() must include screenshots after the port."""
    from collectors import piggyback_collectors

    names = [c.SPEC.name for c in piggyback_collectors()]
    assert "screenshots" in names


def test_screenshots_is_configured_reflects_dir(monkeypatch, tmp_path):
    from collectors import scan_screenshots

    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", tmp_path / "Screenshots")
    assert scan_screenshots.ScreenshotsCollector().is_configured() is False

    (tmp_path / "Screenshots").mkdir()
    assert scan_screenshots.ScreenshotsCollector().is_configured() is True


def test_screenshots_run_skips_when_not_configured(monkeypatch, tmp_path):
    from collectors import scan_screenshots

    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", tmp_path / "nonexistent")
    result = scan_screenshots.ScreenshotsCollector().run()
    assert result.files_written == ()
    assert "not found" in result.message


def test_screenshots_run_maps_scan_result_with_report(monkeypatch, tmp_path):
    """run() should turn scan()'s result dict into a RunResult with the report path."""
    from collectors import scan_screenshots

    sshots = tmp_path / "Screenshots"
    sshots.mkdir()
    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", sshots)

    report = tmp_path / "screenshots-2026-05-14T1200.md"
    report.write_text("# batch", encoding="utf-8")

    captured = {}

    def fake_scan(*, scan_all=False, dry_run=False, limit=0, **kw):
        captured["scan_all"] = scan_all
        captured["dry_run"] = dry_run
        return {"processed": 3, "report_path": report,
                "message": "3 screenshot(s) processed (2 keep, 1 ephemeral) → screenshots-...md"}

    monkeypatch.setattr(scan_screenshots, "scan", fake_scan)

    result = scan_screenshots.ScreenshotsCollector().run()
    assert result.files_written == (report,)
    assert result.files_skipped == 0
    assert "3 screenshot(s) processed" in result.message
    # The Collector path mirrors the legacy `--all` piggyback invocation.
    assert captured["scan_all"] is True
    assert captured["dry_run"] is False


def test_screenshots_run_maps_empty_scan_result(monkeypatch, tmp_path):
    """No report (e.g. Ollama unreachable) → files_skipped=1, no files_written."""
    from collectors import scan_screenshots

    sshots = tmp_path / "Screenshots"
    sshots.mkdir()
    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", sshots)
    monkeypatch.setattr(
        scan_screenshots, "scan",
        lambda **kw: {"processed": 0, "report_path": None, "message": "Ollama not reachable at ..."},
    )

    result = scan_screenshots.ScreenshotsCollector().run()
    assert result.files_written == ()
    assert result.files_skipped == 1
    assert "Ollama not reachable" in result.message


def test_screenshots_run_dry_run_passthrough(monkeypatch, tmp_path):
    """dry_run flag must reach scan()."""
    from collectors import scan_screenshots

    sshots = tmp_path / "Screenshots"
    sshots.mkdir()
    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", sshots)

    seen = {}

    def fake_scan(*, scan_all=False, dry_run=False, limit=0, **kw):
        seen["dry_run"] = dry_run
        return {"processed": 0, "report_path": None, "message": "[dry-run] 5 would be processed"}

    monkeypatch.setattr(scan_screenshots, "scan", fake_scan)

    result = scan_screenshots.ScreenshotsCollector().run(dry_run=True)
    assert seen["dry_run"] is True
    assert "[dry-run]" in result.message


# ── pure helpers ────────────────────────────────────────────────────


def test_parse_screenshot_timestamp_valid():
    from collectors import scan_screenshots

    p = Path("Screenshot 2026-04-16 at 19.04.05.png")
    ts = scan_screenshots.parse_screenshot_timestamp(p)
    assert ts is not None
    assert (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second) == (2026, 4, 16, 19, 4, 5)


def test_parse_screenshot_timestamp_invalid_name():
    from collectors import scan_screenshots

    assert scan_screenshots.parse_screenshot_timestamp(Path("random-file.png")) is None
