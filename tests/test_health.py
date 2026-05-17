"""Tests for scripts/core/health.py — per-check behavior + orchestration.

Each check is exercised against a monkeypatched fixture vault. The TCP
probe (ollama) is skipped via --quick because real network state is
unreliable in CI; behaviour under reachable/unreachable hosts is
exercised separately by stubbing socket.create_connection.
"""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.health as health


@pytest.fixture
def fake_vault(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    logs = tmp_path / ".wiki" / "logs"
    state_dir = tmp_path / ".wiki" / "state"
    for d in (knowledge, logs, state_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(health, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(health, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(health, "LOGS_DIR", logs)
    monkeypatch.setattr(health, "STATE_FILE", state_dir / "state.json")
    monkeypatch.setattr(health, "WIKI_DIR", tmp_path / ".wiki")
    return tmp_path


# ── check_setup_run ────────────────────────────────────────────────


def test_setup_run_critical_when_default_config_and_no_state(fake_vault, monkeypatch):
    # Stub CONFIG to look like defaults.
    class _Models:
        ollama_url = ""
        compile_model = "claude-opus-4-7"

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    result = health.check_setup_run()
    assert result.severity == "critical"
    assert result.fix == "wiki setup"


def test_setup_run_ok_when_state_exists(fake_vault, monkeypatch):
    health.STATE_FILE.write_text("{}")

    class _Models:
        ollama_url = ""
        compile_model = "claude-opus-4-7"

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    result = health.check_setup_run()
    assert result.severity == "ok"


# ── check_hooks_installed ──────────────────────────────────────────


def test_hooks_warning_when_no_wiki_hooks(fake_vault):
    (fake_vault / ".claude").mkdir()
    (fake_vault / ".claude" / "settings.json").write_text('{"hooks": {}}')
    result = health.check_hooks_installed()
    assert result.severity == "warning"
    assert "wiki hooks install" in result.fix


def test_hooks_ok_when_wiki_managed_entry_present(fake_vault):
    (fake_vault / ".claude").mkdir()
    (fake_vault / ".claude" / "settings.json").write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"command": "uv run --project '
        '/x/.wiki python /x/.wiki/hooks/session-start.py"}]}]}}'
    )
    result = health.check_hooks_installed()
    assert result.severity == "ok"
    assert "claude" in result.details["agents"]


def test_hooks_detects_multiple_agents(fake_vault):
    for agent in ("claude", "cursor"):
        d = fake_vault / f".{agent}"
        d.mkdir()
        (d / ("settings.json" if agent == "claude" else "hooks.json")).write_text(
            '{"hooks": {"x": [".wiki/hooks/session-start.py"]}}'
        )
    result = health.check_hooks_installed()
    assert result.severity == "ok"
    assert set(result.details["agents"]) == {"claude", "cursor"}


# ── check_claude_authed ────────────────────────────────────────────


def test_claude_ok_when_env_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    result = health.check_claude_authed()
    assert result.severity == "ok"
    assert "env" in result.message


def test_claude_ok_when_creds_file_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    creds_dir = tmp_path / ".claude"
    creds_dir.mkdir()
    (creds_dir / ".credentials.json").write_text("{}")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    result = health.check_claude_authed()
    assert result.severity == "ok"


def test_claude_quick_warning_without_env_or_creds(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    result = health.check_claude_authed(quick=True)
    assert result.severity == "warning"
    assert "quick" in result.message.lower()


# ── check_ollama_reachable ─────────────────────────────────────────


def test_ollama_quick_mode_skips(fake_vault, monkeypatch):
    result = health.check_ollama_reachable(quick=True)
    assert result.severity == "info"
    assert "skipped" in result.message.lower()


def test_ollama_info_when_not_configured(fake_vault, monkeypatch):
    class _Models:
        ollama_url = ""

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    result = health.check_ollama_reachable()
    assert result.severity == "info"


def test_ollama_warning_when_unreachable(fake_vault, monkeypatch):
    class _Models:
        ollama_url = "http://nonexistent-host-12345:11434"

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())

    def _refuse(*_a, **_kw):
        raise OSError("test: unreachable")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    result = health.check_ollama_reachable()
    assert result.severity == "warning"
    assert "unreachable" in result.message


# ── check_compile_errors_recent ────────────────────────────────────


def test_compile_errors_ok_when_log_missing(fake_vault):
    result = health.check_compile_errors_recent()
    assert result.severity == "ok"


def test_compile_errors_warning_on_recent_lines(fake_vault):
    today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    err_log = health.LOGS_DIR / "compile-errors.log"
    err_log.write_text(
        f"{today}  ERROR  compile_file foo.md kind=unknown\n"
        f"{today}  ERROR  compile_file bar.md kind=rate_limit\n"
    )
    result = health.check_compile_errors_recent()
    assert result.severity == "warning"
    assert result.details["count"] == 2


def test_compile_errors_ignores_old_entries(fake_vault):
    old = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S")
    err_log = health.LOGS_DIR / "compile-errors.log"
    err_log.write_text(f"{old}  ERROR  ancient\n")
    # Backdate file mtime too so the early-exit path fires.
    age = time.time() - 20 * 86400
    os.utime(err_log, (age, age))
    result = health.check_compile_errors_recent()
    assert result.severity == "ok"


# ── check_no_knowledge_articles + check_compile_state ──────────────


def test_no_knowledge_info_when_empty(fake_vault):
    result = health.check_no_knowledge_articles()
    assert result.severity == "info"
    assert "fresh vault" in result.message


def test_no_knowledge_ok_when_articles_present(fake_vault):
    (fake_vault / "knowledge" / "concepts").mkdir(parents=True)
    (fake_vault / "knowledge" / "concepts" / "a.md").write_text("x")
    (fake_vault / "knowledge" / "index.md").write_text("x")  # excluded
    result = health.check_no_knowledge_articles()
    assert result.severity == "ok"
    assert result.details["count"] == 1


def test_compile_state_info_when_no_state(fake_vault):
    result = health.check_compile_state()
    assert result.severity == "info"


def test_compile_state_info_when_stale(fake_vault):
    past = (datetime.now() - timedelta(days=40)).replace(microsecond=0).isoformat()
    health.STATE_FILE.write_text(json.dumps({"last_compile": past}))
    result = health.check_compile_state()
    assert result.severity == "info"
    assert "consider" in result.message


def test_compile_state_ok_when_recent(fake_vault):
    recent = datetime.now().replace(microsecond=0).isoformat()
    health.STATE_FILE.write_text(json.dumps({"last_compile": recent}))
    result = health.check_compile_state()
    assert result.severity == "ok"


# ── orchestration ──────────────────────────────────────────────────


def test_build_health_returns_list_sorted_by_severity(fake_vault, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    results = health.build_health(quick=True)
    severities = [r.severity for r in results]
    order = [health.SEVERITY_ORDER[s] for s in severities]
    assert order == sorted(order), f"results not sorted by severity: {severities}"


def test_health_summary_counts_each_severity(fake_vault):
    sample = [
        health.CheckResult("a", "config", "critical", "x"),
        health.CheckResult("b", "config", "warning", "x"),
        health.CheckResult("c", "config", "warning", "x"),
        health.CheckResult("d", "config", "ok", "x"),
    ]
    summary = health.health_summary(sample)
    assert summary == {"critical": 1, "warning": 2, "info": 0, "ok": 1}


def test_to_json_serializable(fake_vault):
    sample = [health.CheckResult("a", "config", "ok", "x", fix="y", details={"k": 1})]
    out = health.to_json(sample)
    assert out == [{
        "id": "a", "category": "config", "severity": "ok",
        "message": "x", "fix": "y", "dispatch_args": None, "details": {"k": 1},
    }]
    json.dumps(out)  # round-trips through json


def test_to_json_includes_dispatch_args():
    sample = [health.CheckResult(
        "a", "config", "warning", "x",
        fix="wiki setup", dispatch_args=["setup"],
    )]
    out = health.to_json(sample)
    assert out[0]["dispatch_args"] == ["setup"]


def test_check_setup_run_carries_dispatch_args(fake_vault, monkeypatch):
    """The promoted-to-actionable checks set both `fix` (human-readable)
    and `dispatch_args` (concrete invocation)."""
    class _Models:
        ollama_url = ""
        compile_model = "claude-opus-4-7"

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    result = health.check_setup_run()
    assert result.severity == "critical"
    assert result.dispatch_args == ["setup"]


def test_check_hooks_dispatch_args_when_missing(fake_vault):
    result = health.check_hooks_installed()
    assert result.severity == "warning"
    assert result.dispatch_args == ["hooks", "install"]


def test_unactionable_checks_have_no_dispatch_args(fake_vault, monkeypatch):
    """Multi-step / external / shell-only fixes have fix= set but dispatch_args=None
    so the banner doesn't try to auto-run them."""
    # ollama-unreachable
    class _Models:
        ollama_url = "http://nonexistent-host-12345:11434"

    class _CONFIG:
        models = _Models()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())

    def _refuse(*_a, **_kw):
        raise OSError("test: unreachable")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    result = health.check_ollama_reachable()
    assert result.severity == "warning"
    assert result.dispatch_args is None  # not auto-runnable


def test_probe_failed_returns_warning_with_exception_text(fake_vault):
    result = health._probe_failed("test-id", "config", RuntimeError("boom"))
    assert result.severity == "warning"
    assert "boom" in result.message
