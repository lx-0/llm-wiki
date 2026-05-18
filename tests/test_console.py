"""Tests for `core.console` shared CLI formatter.

The module captures sys.stderr.isatty() at import time, so we patch the
module-level constants directly to simulate TTY vs non-TTY conditions
rather than re-importing under a fake stderr.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import console  # noqa: E402


def _make_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


@pytest.fixture
def tty_mode(monkeypatch):
    """Force TTY mode for ANSI tests regardless of the test runner's terminal."""
    monkeypatch.setattr(console, "_TTY", True)
    monkeypatch.setattr(console, "C_RESET", "\033[0m")
    monkeypatch.setattr(console, "C_DIM", "\033[2m")
    monkeypatch.setattr(console, "C_BOLD", "\033[1m")
    monkeypatch.setattr(console, "C_RED", "\033[31m")
    monkeypatch.setattr(console, "C_GREEN", "\033[32m")
    monkeypatch.setattr(console, "C_YELLOW", "\033[33m")
    monkeypatch.setattr(console, "C_CYAN", "\033[36m")


@pytest.fixture
def plain_mode(monkeypatch):
    """Force non-TTY mode to verify clean output for log captures."""
    monkeypatch.setattr(console, "_TTY", False)
    for name in ("C_RESET", "C_DIM", "C_BOLD", "C_RED", "C_GREEN", "C_YELLOW", "C_CYAN"):
        monkeypatch.setattr(console, name, "")


class TestNonTtyPlainOutput:
    def test_info_has_no_ansi(self, plain_mode):
        out = console.ConsoleFormatter().format(_make_record("hello world"))
        assert "\033[" not in out
        assert "hello world" in out

    def test_warning_has_label_without_color_codes(self, plain_mode):
        out = console.ConsoleFormatter().format(
            _make_record("careful now", level=logging.WARNING)
        )
        assert "\033[" not in out
        assert "WARNING" in out

    def test_checkmark_remains_plain(self, plain_mode):
        out = console.ConsoleFormatter().format(_make_record("  ✓ done in 1.2s"))
        assert "\033[" not in out
        assert "✓" in out


class TestTtyColorization:
    def test_info_label_suppressed(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("hello"))
        # INFO records show no level label (only timestamp + message).
        assert "INFO" not in out

    def test_warning_label_colored(self, tty_mode):
        out = console.ConsoleFormatter().format(
            _make_record("watch out", level=logging.WARNING)
        )
        assert "\033[33m" in out  # yellow
        assert "WARNING" in out

    def test_error_label_colored(self, tty_mode):
        out = console.ConsoleFormatter().format(
            _make_record("broken", level=logging.ERROR)
        )
        assert "\033[31m" in out  # red
        assert "ERROR" in out

    def test_checkmark_green(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("  ✓ done"))
        assert "\033[32m✓\033[0m" in out

    def test_xmark_red(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("  ✗ failed"))
        assert "\033[31m✗\033[0m" in out

    def test_section_banner_bolded(self, tty_mode):
        out = console.ConsoleFormatter().format(
            _make_record("─── compiling 10 of 50 ───")
        )
        assert "\033[1m" in out  # bold

    def test_elapsed_dimmed(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("done after 12.5s"))
        assert "\033[2m12.5s\033[0m" in out

    def test_tokens_dimmed(self, tty_mode):
        out = console.ConsoleFormatter().format(
            _make_record("usage: in:1,200 out:300 fini")
        )
        assert "\033[2min:1,200 out:300\033[0m" in out


class TestCostTiering:
    @pytest.mark.parametrize("amount,expected_color", [
        ("0.01", "\033[2m"),    # < $0.05 — dim
        ("0.04", "\033[2m"),    # < $0.05 — dim
        ("0.10", None),         # mid — plain (no color wrap)
        ("0.49", None),         # just under $0.50 — plain
        ("0.50", "\033[33m"),   # ≥ $0.50 — yellow
        ("1.49", "\033[33m"),   # just under $1.50 — yellow
        ("1.50", "\033[1m\033[33m"),  # ≥ $1.50 — bold + yellow
        ("12.34", "\033[1m\033[33m"), # high cost — bold + yellow
    ])
    def test_tier_colors(self, tty_mode, amount, expected_color):
        out = console.ConsoleFormatter().format(
            _make_record(f"cost: (${amount}) reported")
        )
        if expected_color is None:
            # No color wrap — just the literal substring stays plain.
            assert f"(${amount})" in out
            # Should NOT contain a color escape adjacent to this cost.
            assert f"\033[33m${amount}" not in out
            assert f"\033[2m${amount}" not in out
        else:
            assert f"({expected_color}${amount}\033[0m)" in out


class TestSdkNoiseFilter:
    def test_drops_bundled_cli_line(self):
        f = console.SdkNoiseFilter()
        rec = _make_record(
            "Using bundled Claude Code CLI: /some/long/path/cli.js"
        )
        assert f.filter(rec) is False

    def test_keeps_other_lines(self):
        f = console.SdkNoiseFilter()
        rec = _make_record("compile_file ✗ failed")
        assert f.filter(rec) is True


class TestSubclassExtras:
    def test_extras_hook_owns_the_line_when_returns_string(self, tty_mode):
        class Subclass(console.ConsoleFormatter):
            def _format_message_extras(self, msg: str) -> str | None:
                if msg.startswith(">>>"):
                    return f"OVERRIDE: {msg}"
                return None

        out = Subclass().format(_make_record(">>> custom line"))
        assert "OVERRIDE: >>> custom line" in out
        # Generic colorization should NOT also run when extras matched —
        # the ✓/✗ replacement should not apply (no ✓ here anyway).

    def test_extras_hook_falls_through_when_none(self, tty_mode):
        class Subclass(console.ConsoleFormatter):
            def _format_message_extras(self, msg: str) -> str | None:
                return None  # always fall through

        out = Subclass().format(_make_record("  ✓ ok"))
        assert "\033[32m✓\033[0m" in out  # generic colorization ran


class TestSetupHelper:
    def test_adds_console_handler(self, tmp_path, monkeypatch):
        # Use a unique logger name to avoid root pollution across tests.
        root = logging.getLogger()
        existing_handlers = list(root.handlers)
        monkeypatch.setattr(root, "handlers", [])
        try:
            console.setup_console_logging("my-cli")
            assert any(
                isinstance(h, logging.StreamHandler) for h in root.handlers
            )
        finally:
            root.handlers = existing_handlers

    def test_creates_log_file_handler(self, tmp_path, monkeypatch):
        root = logging.getLogger()
        existing_handlers = list(root.handlers)
        monkeypatch.setattr(root, "handlers", [])
        try:
            log_path = tmp_path / "subdir" / "test.log"
            console.setup_console_logging("my-cli", log_file=log_path)
            file_handlers = [
                h for h in root.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert Path(file_handlers[0].baseFilename) == log_path
            assert log_path.parent.exists()  # mkdir(parents=True) ran
        finally:
            root.handlers = existing_handlers
            logging.shutdown()
