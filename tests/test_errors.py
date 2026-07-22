"""core.errors.swallow — the labeled intentional-suppression seam.

Contract: suppress Exception (never KeyboardInterrupt/SystemExit), log
one line carrying the label at the requested level, stay silent when
the block succeeds. Works as context manager and as decorator.
"""

from __future__ import annotations

import logging

import pytest

from core.errors import swallow


def test_suppresses_exception_and_logs_label_at_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="core.errors"):
        with swallow("test-site"):
            raise ValueError("boom")
    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert rec.levelno == logging.WARNING
    assert "test-site" in rec.getMessage()
    assert "ValueError" in rec.getMessage()
    assert "boom" in rec.getMessage()


def test_no_exception_no_log(caplog):
    with caplog.at_level(logging.DEBUG, logger="core.errors"):
        with swallow("quiet-site"):
            pass
    assert caplog.records == []


def test_debug_level_logs_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger="core.errors"):
        with swallow("cleanup-site", level="debug"):
            raise OSError("socket gone")
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG


def test_keyboard_interrupt_propagates_unlogged(caplog):
    with caplog.at_level(logging.DEBUG, logger="core.errors"):
        with pytest.raises(KeyboardInterrupt):
            with swallow("interrupt-site"):
                raise KeyboardInterrupt
    assert caplog.records == []


def test_system_exit_propagates_unlogged(caplog):
    with caplog.at_level(logging.DEBUG, logger="core.errors"):
        with pytest.raises(SystemExit):
            with swallow("exit-site"):
                raise SystemExit(3)
    assert caplog.records == []


def test_decorator_form_suppresses_and_returns_none(caplog):
    @swallow("decorated-site")
    def blows_up() -> str:
        raise RuntimeError("kaputt")

    with caplog.at_level(logging.WARNING, logger="core.errors"):
        assert blows_up() is None
    assert len(caplog.records) == 1
    assert "decorated-site" in caplog.records[0].getMessage()


def test_decorator_form_passes_through_return_value():
    @swallow("ok-site")
    def fine() -> int:
        return 42

    assert fine() == 42


def test_invalid_level_raises_at_construction():
    with pytest.raises(ValueError, match="swallow level"):
        swallow("bad", level="verbose")


def test_logger_override_routes_to_given_logger(caplog):
    custom = logging.getLogger("test.swallow.custom")
    with caplog.at_level(logging.WARNING, logger="test.swallow.custom"):
        with swallow("routed-site", logger=custom):
            raise KeyError("missing")
    assert len(caplog.records) == 1
    assert caplog.records[0].name == "test.swallow.custom"


# ── Spot checks: previously-silent sites now log ─────────────────────
# The C14 mechanical pass converted 14 silent-pass + ~29 unlogged
# bare-return sites. One representative per converted shape proves the
# behaviour change (failure -> log line) end-to-end.


def test_health_probe_failure_logs_and_degrades(caplog, monkeypatch):
    """A crashing health check logs a WARNING (was: unlogged CheckResult)."""
    from core import health

    def broken_check():
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(health, "_ALL_CHECKS", [broken_check])
    with caplog.at_level(logging.WARNING, logger="core.health"):
        results = health.build_health()
    assert len(results) == 1
    assert results[0].severity == "warning"
    assert any(
        "broken_check" in r.getMessage() and "probe exploded" in r.getMessage()
        for r in caplog.records
    )


def test_usage_exit_flush_failure_logs_instead_of_vanishing(caplog, monkeypatch):
    """A failing atexit ledger persist logs (was: except-pass) and never raises."""
    from core import usage

    def boom() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(usage.LEDGER, "persist", boom)
    with caplog.at_level(logging.WARNING, logger="core.errors"):
        usage._flush_on_exit()
    assert any("usage-ledger exit flush" in r.getMessage() for r in caplog.records)


def test_backfill_frontmatter_parse_failure_logs(tmp_path, caplog):
    """Malformed YAML frontmatter logs the file path (was: silent {} return)."""
    import backfill_daily_rollup as mod

    bad = tmp_path / "note.md"
    bad.write_text("---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="backfill_daily_rollup"):
        out = mod._read_frontmatter(bad)
    assert out == {}
    assert any(
        "frontmatter parse failed" in r.getMessage() and str(bad) in r.getMessage()
        for r in caplog.records
    )


def test_gmail_internal_date_fallback_logs_debug(caplog):
    """Unparseable internalDate falls back to epoch AND leaves a debug line."""
    from datetime import datetime

    from adapters.mailbox import gmail

    with caplog.at_level(logging.DEBUG, logger="adapters.mailbox.gmail"):
        dt = gmail._parse_internal_date("not-a-number")
    assert dt == datetime.fromtimestamp(0)
    assert any("internalDate parse failed" in r.getMessage() for r in caplog.records)
