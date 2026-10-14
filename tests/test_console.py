"""Tests for `core.console` shared CLI formatter.

The module captures sys.stderr.isatty() at import time, so we patch the
module-level constants directly to simulate TTY vs non-TTY conditions
rather than re-importing under a fake stderr.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from core import console

ROOT = Path(__file__).resolve().parent.parent
# `setup_console_logging(` / `log = setup_console_logging(` at column 0 — a call at import.
_MODULE_LEVEL_SETUP = re.compile(r"^(?:\w+\s*=\s*)?setup_console_logging\(")


def _make_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
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
        out = console.ConsoleFormatter().format(_make_record("careful now", level=logging.WARNING))
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
        out = console.ConsoleFormatter().format(_make_record("watch out", level=logging.WARNING))
        assert "\033[33m" in out  # yellow
        assert "WARNING" in out

    def test_error_label_colored(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("broken", level=logging.ERROR))
        assert "\033[31m" in out  # red
        assert "ERROR" in out

    def test_checkmark_green(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("  ✓ done"))
        assert "\033[32m✓\033[0m" in out

    def test_xmark_red(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("  ✗ failed"))
        assert "\033[31m✗\033[0m" in out

    def test_section_banner_bolded(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("─── compiling 10 of 50 ───"))
        assert "\033[1m" in out  # bold

    def test_elapsed_dimmed(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("done after 12.5s"))
        assert "\033[2m12.5s\033[0m" in out

    def test_tokens_dimmed(self, tty_mode):
        out = console.ConsoleFormatter().format(_make_record("usage: in:1,200 out:300 fini"))
        assert "\033[2min:1,200 out:300\033[0m" in out


class TestCostTiering:
    @pytest.mark.parametrize(
        "amount,expected_color",
        [
            ("0.01", "\033[2m"),  # < $0.05 — dim
            ("0.04", "\033[2m"),  # < $0.05 — dim
            ("0.10", None),  # mid — plain (no color wrap)
            ("0.49", None),  # just under $0.50 — plain
            ("0.50", "\033[33m"),  # ≥ $0.50 — yellow
            ("1.49", "\033[33m"),  # just under $1.50 — yellow
            ("1.50", "\033[1m\033[33m"),  # ≥ $1.50 — bold + yellow
            ("12.34", "\033[1m\033[33m"),  # high cost — bold + yellow
        ],
    )
    def test_tier_colors(self, tty_mode, amount, expected_color):
        out = console.ConsoleFormatter().format(_make_record(f"cost: (${amount}) reported"))
        if expected_color is None:
            # Mid-tier ($0.10–$0.49): no color wrap.
            assert f"${amount}" in out
            # Should NOT contain a yellow/dim color escape adjacent to this cost.
            assert f"\033[33m${amount}" not in out
            assert f"\033[2m${amount}" not in out
        else:
            # Surrounding parens stay plain; the dollar amount itself is colored.
            assert f"{expected_color}${amount}\033[0m" in out


class TestSdkNoiseFilter:
    def test_drops_bundled_cli_line(self):
        f = console.SdkNoiseFilter()
        rec = _make_record("Using bundled Claude Code CLI: /some/long/path/cli.js")
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
            assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
        finally:
            root.handlers = existing_handlers

    def test_creates_log_file_handler(self, tmp_path, monkeypatch):
        root = logging.getLogger()
        existing_handlers = list(root.handlers)
        monkeypatch.setattr(root, "handlers", [])
        try:
            log_path = tmp_path / "subdir" / "test.log"
            console.setup_console_logging("my-cli", log_file=log_path)
            file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
            assert len(file_handlers) == 1
            assert Path(file_handlers[0].baseFilename) == log_path
            assert log_path.parent.exists()  # mkdir(parents=True) ran
        finally:
            root.handlers = existing_handlers
            logging.shutdown()

    def test_second_call_is_idempotent_on_stderr_handler(self, monkeypatch):
        """Regression for incident 2026-05-18: dream.py lazy-imported compile.py,
        triggering a second setup_console_logging call that stacked a second
        stderr handler. Every log line afterwards double-emitted on stderr.
        Setup must reuse the existing stderr handler instead of adding another."""
        root = logging.getLogger()
        existing_handlers = list(root.handlers)
        monkeypatch.setattr(root, "handlers", [])
        try:
            console.setup_console_logging("first-cli")
            stderr_handlers_after_first = [
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            ]
            assert len(stderr_handlers_after_first) == 1
            first_formatter = stderr_handlers_after_first[0].formatter

            # Second call (simulates the lazy cross-import that caused the bug)
            console.setup_console_logging("second-cli", formatter=console.ConsoleFormatter())
            stderr_handlers_after_second = [
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            ]
            # No new stderr handler — would have been the bug.
            assert len(stderr_handlers_after_second) == 1
            # First-call's formatter still wins (importing CLI's style stays).
            assert stderr_handlers_after_second[0].formatter is first_formatter
        finally:
            root.handlers = existing_handlers
            logging.shutdown()

    def test_second_call_dedupes_file_handlers_by_path(self, tmp_path, monkeypatch):
        """Same file_path on a second call must not pile a second FileHandler."""
        root = logging.getLogger()
        existing_handlers = list(root.handlers)
        monkeypatch.setattr(root, "handlers", [])
        try:
            log_path = tmp_path / "shared.log"
            console.setup_console_logging("first-cli", log_file=log_path)
            console.setup_console_logging("second-cli", log_file=log_path)
            file_handlers = [
                h
                for h in root.handlers
                if isinstance(h, logging.FileHandler) and h.baseFilename == str(log_path.resolve())
            ]
            assert len(file_handlers) == 1
        finally:
            root.handlers = existing_handlers
            logging.shutdown()


class TestOneSetupEverywhere:
    """M033-S03-T04: the seam is the engine's one logging setup."""

    def test_level_keyword_sets_the_root_level(self, monkeypatch):
        """The home-screen probe (menu_context) runs at WARNING so its INFO never reaches
        the operator's terminal — the seam carries the level instead of a private
        basicConfig."""
        root = logging.getLogger()
        existing_handlers, existing_level = list(root.handlers), root.level
        monkeypatch.setattr(root, "handlers", [])
        try:
            console.setup_console_logging("quiet-cli", level=logging.WARNING)
            assert root.level == logging.WARNING
        finally:
            root.handlers = existing_handlers
            root.setLevel(existing_level)

    def test_no_module_under_scripts_calls_basicconfig(self):
        """Every CLI goes through setup_console_logging; a `logging.basicConfig` anywhere
        under scripts/ is a second setup — and at module level the root-logger footgun
        KNOWLEDGE records ("no basicConfig in importable modules")."""
        offenders = [
            f"{p.relative_to(ROOT)}:{n}"
            for p in sorted((ROOT / "scripts").rglob("*.py"))
            if p.name != "console.py"
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if "logging.basicConfig(" in line
        ]
        assert offenders == [], "logging.basicConfig outside core/console.py:\n" + "\n".join(
            offenders
        )

    def test_no_module_level_setup_console_logging(self):
        """The seam is called from an entry point, never at import: a module-level
        `setup_console_logging(...)` (bare or `log = …`) configures the root logger of
        whoever imports the module — lint ← reconcile, flush ← retry_failed_flushes,
        preprocessors.inbox ← its package, compile / dream / query ← the tests. A call
        at column 0 is the smell; an indented call sits inside an entry function."""
        offenders = [
            f"{p.relative_to(ROOT)}:{n}"
            for p in sorted((ROOT / "scripts").rglob("*.py"))
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if _MODULE_LEVEL_SETUP.match(line)
        ]
        assert offenders == [], "module-level setup_console_logging:\n" + "\n".join(offenders)

    @pytest.mark.parametrize(
        "module",
        ["menu_context", "facts.correct_apply", "compile", "lint", "flush", "preprocessors.inbox"],
    )
    def test_importing_an_engine_module_configures_no_root_handler(self, module: str):
        """These modules are imported by other modules (menu_context by menu.py and the
        oracle, facts.correct_apply by reconcile, compile by the maintenance tests, lint by
        reconcile, flush by retry_failed_flushes, preprocessors.inbox by its package): a
        setup at import configured the importer's root logger. Checked in a fresh
        interpreter — under pytest the root already has handlers and a basicConfig would
        silently no-op, hiding exactly this."""
        code = f"import logging, {module}; print(len(logging.getLogger().handlers))"
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")},
            check=False,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "0", f"importing {module} configured the root logger"
