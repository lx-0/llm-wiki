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


def test_hooks_warning_when_no_wiki_hooks(fake_vault, monkeypatch):
    # Isolate Path.home() so the operator's real ~/.claude/ doesn't bleed in.
    fake_home = fake_vault / "_fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    (fake_vault / ".claude").mkdir()
    (fake_vault / ".claude" / "settings.json").write_text('{"hooks": {}}')
    result = health.check_hooks_installed()
    assert result.severity == "warning"
    assert "wiki hooks install" in result.fix


def test_hooks_ok_for_project_scope_direct_path(fake_vault, monkeypatch):
    """Current install format: `--project .wiki python .wiki/hooks/<name>.py`."""
    fake_home = fake_vault / "_fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    (fake_vault / ".claude").mkdir()
    (fake_vault / ".claude" / "settings.json").write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"command": "uv run --project '
        '/x/.wiki python /x/.wiki/hooks/session-start.py"}]}]}}'
    )
    result = health.check_hooks_installed()
    assert result.severity == "ok"
    assert "claude" in result.details["project"]
    assert result.details["user"] == []


def test_hooks_ok_for_user_scope_cd_form(fake_vault, monkeypatch):
    """Operator real-world style: cd-anchored absolute path in user scope
    (~/.claude/settings.json points at one specific vault). Project-scope
    file may exist without wiki entries (= 'detected' in `wiki hooks status`)."""
    fake_home = fake_vault / "_fake_home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    (fake_home / ".claude" / "settings.json").write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"command": '
        "\"cd '/Users/alex/.../lxw/.wiki' && uv run python hooks/session-start.py\""
        "}]}]}}"
    )
    # Project-scope file exists but has no wiki entries — the "detected" case.
    (fake_vault / ".claude").mkdir()
    (fake_vault / ".claude" / "settings.json").write_text('{"hooks": {}}')
    result = health.check_hooks_installed()
    assert result.severity == "ok"
    assert "claude" in result.details["user"]
    assert result.details["project"] == []


def test_hooks_detects_multiple_agents_across_scopes(fake_vault, monkeypatch):
    fake_home = fake_vault / "_fake_home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    # claude in user scope (cd-style)
    (fake_home / ".claude" / "settings.json").write_text(
        '{"x": "cd \'/v/.wiki\' && uv run python hooks/session-start.py"}'
    )
    # cursor in project scope (direct-path style)
    (fake_vault / ".cursor").mkdir()
    (fake_vault / ".cursor" / "hooks.json").write_text(
        '{"x": ".wiki/hooks/session-end.py"}'
    )
    result = health.check_hooks_installed()
    assert result.severity == "ok"
    assert result.details["user"] == ["claude"]
    assert result.details["project"] == ["cursor"]


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


def test_ollama_connect_budget_is_not_a_hair_trigger(fake_vault, monkeypatch):
    """Live 2026-08-26: the check used a hardcoded 150 ms TCP budget while
    `limits.ollama_connect_timeout_s` (10 s) existed for exactly this. Against
    a healthy LAN host answering in 6-41 ms, 2 of 12 connects still blew past
    150 ms and were reported `unreachable` — a ~17% false-alarm rate on the
    one check that is supposed to tell the operator their GPU box is down. The
    budget derives from config, floors well above LAN jitter, and stays capped
    so a genuinely dead host can't stall the health screen."""
    class _Models:
        ollama_url = "http://192.168.2.42:11434"

    class _Limits:
        ollama_connect_timeout_s = 10

    class _CONFIG:
        models = _Models()
        limits = _Limits()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())

    seen = {}

    class _Sock:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _capture(address, timeout=None, **kw):
        seen["timeout"] = timeout
        return _Sock()

    monkeypatch.setattr(socket, "create_connection", _capture)
    result = health.check_ollama_reachable()

    assert result.severity == "ok"
    assert seen["timeout"] >= 1.0, (
        f"connect budget {seen['timeout']}s is below LAN jitter — false 'unreachable'"
    )
    assert seen["timeout"] <= _Limits.ollama_connect_timeout_s
    assert seen["timeout"] <= 5.0, "health screen must not stall on a dead host"


def test_ollama_connect_budget_respects_a_lower_config(fake_vault, monkeypatch):
    """An operator who tightens the knob is honoured, not overridden."""
    class _Models:
        ollama_url = "http://192.168.2.42:11434"

    class _Limits:
        ollama_connect_timeout_s = 2

    class _CONFIG:
        models = _Models()
        limits = _Limits()

    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())

    seen = {}

    class _Sock:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(socket, "create_connection",
                        lambda address, timeout=None, **kw: (seen.update(timeout=timeout), _Sock())[1])
    health.check_ollama_reachable()
    assert seen["timeout"] == 2


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


def test_check_hooks_dispatch_args_when_missing(fake_vault, monkeypatch):
    # Isolate Path.home so the operator's real ~/.claude/ doesn't bleed in.
    fake_home = fake_vault / "_fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
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


# ── check_account_auths (multi-result probe) ─────────────────────────


def test_account_auths_empty_when_no_accounts(fake_vault, monkeypatch):
    class _Personal: accounts = {}
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    out = health.check_account_auths()
    assert out == []


def test_account_auths_emits_ok_when_token_exists(fake_vault, monkeypatch):
    class _Personal:
        accounts = {"work": {"calendar": {"kind": "google-calendar"}}}
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)
    (state / "calendar-token-work.json").write_text('{"token": "x"}')

    out = health.check_account_auths()
    assert len(out) == 1
    assert out[0].id == "account-auth-work-calendar"
    assert out[0].severity == "ok"
    assert out[0].dispatch_args is None


def test_account_auths_emits_warning_with_dispatch_args_when_missing(fake_vault, monkeypatch):
    class _Personal:
        accounts = {"work": {"gmeet": {"kind": "gmeet-api"}}}
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)
    # no token file present

    out = health.check_account_auths()
    assert len(out) == 1
    assert out[0].severity == "warning"
    assert out[0].dispatch_args == ["gmeet-auth", "work"]
    assert "wiki gmeet-auth work" in out[0].fix


def test_account_auths_handles_multi_account_multi_integration(fake_vault, monkeypatch):
    class _Personal:
        accounts = {
            "work": {
                "calendar": {"kind": "google-calendar"},
                "gmeet": {"kind": "gmeet-api"},
            },
            "home": {
                "calendar": {"kind": "google-calendar"},
            },
        }
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)
    # work calendar has token; the other two don't
    (state / "calendar-token-work.json").write_text("{}")

    out = health.check_account_auths()
    ids = sorted(r.id for r in out)
    assert ids == [
        "account-auth-home-calendar",
        "account-auth-work-calendar",
        "account-auth-work-gmeet",
    ]
    by_id = {r.id: r for r in out}
    assert by_id["account-auth-work-calendar"].severity == "ok"
    assert by_id["account-auth-work-gmeet"].severity == "warning"
    assert by_id["account-auth-home-calendar"].severity == "warning"


def test_account_auths_gmail_detected_via_filter_subblock(fake_vault, monkeypatch):
    """Real-world lxw shape: reader is thunderbird-mbox / IMAP (no Gmail API),
    filter is gmail-api (uses OAuth for label/move push). A missing gmail-token
    degrades ONLY the write-side filter — email READING is unaffected — so this
    reports `info` with accurate wording, not a `warning` claiming the collector
    skips the account."""
    class _Personal:
        accounts = {
            "work": {
                "reader": {"kind": "thunderbird-mbox"},
                "filter": {"kind": "gmail-api"},
            },
        }
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)

    out = health.check_account_auths()
    assert len(out) == 1
    assert out[0].id == "account-auth-work-gmail"
    assert out[0].severity == "info"
    assert "reading" in out[0].message.lower()  # accurate: reading unaffected
    assert "collector will skip" not in out[0].message
    assert out[0].dispatch_args == ["gmail-auth", "work"]


def test_account_auths_gmail_detected_via_reader_subblock(fake_vault, monkeypatch):
    """Alternative shape: reader.kind=gmail-api (mailbox itself is
    Gmail API), no separate filter. Same gmail-token needed."""
    class _Personal:
        accounts = {"work": {"reader": {"kind": "gmail-api"}}}
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)

    out = health.check_account_auths()
    assert len(out) == 1
    assert out[0].id == "account-auth-work-gmail"


def test_account_auths_ignores_non_oauth_integrations(fake_vault, monkeypatch):
    """jamie-api uses an api key (env var), not OAuth — no token cache
    to probe. thunderbird-mbox + imap don't need OAuth either. The
    check must skip them silently rather than emit confusing warnings."""
    class _Personal:
        accounts = {
            "kasserver": {
                "reader": {"kind": "thunderbird-mbox"},
                "filter": {"kind": "all-inkl-procmail"},
            },
            "default": {"jamie": {"kind": "jamie-api"}},
        }
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)

    out = health.check_account_auths()
    assert out == []


def test_build_health_flattens_multi_result_checks(fake_vault, monkeypatch):
    """The orchestrator must handle list-returning probes by extending
    the results, not appending the list as a nested value."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # noise; force claude ok

    class _Personal:
        accounts = {"a": {"calendar": {"kind": "google-calendar"}}}
    class _CONFIG: personal = _Personal()
    monkeypatch.setitem(__import__("sys").modules, "core.config",
                        type("M", (), {"CONFIG": _CONFIG})())
    state = fake_vault / ".wiki" / "state"
    monkeypatch.setattr(health, "STATE_DIR", state)

    results = health.build_health(quick=True)
    # Every entry must be a CheckResult, never a nested list.
    for r in results:
        assert isinstance(r, health.CheckResult), f"non-CheckResult in results: {r!r}"
    account_results = [r for r in results if r.id.startswith("account-auth-")]
    assert len(account_results) == 1


# ── check_wiki_on_path ─────────────────────────────────────────────


def test_wiki_on_path_warning_when_missing(fake_vault, monkeypatch):
    import shutil
    (fake_vault / ".wiki").mkdir(exist_ok=True)
    (fake_vault / ".wiki" / "wiki").write_text("#!/bin/sh")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = health.check_wiki_on_path()
    assert result.severity == "warning"
    assert result.dispatch_args == ["install-shortcut"]
    assert "not on $PATH" in result.message


def test_wiki_on_path_ok_when_resolves_to_this_vault(tmp_path, monkeypatch):
    import shutil
    wiki_dir = tmp_path / ".wiki"
    wiki_dir.mkdir()
    own = wiki_dir / "wiki"
    own.write_text("#!/bin/sh")
    monkeypatch.setattr(health, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(shutil, "which", lambda _name: str(own))
    result = health.check_wiki_on_path()
    assert result.severity == "ok"
    assert str(own) in result.message


def test_wiki_on_path_warning_when_resolves_elsewhere(tmp_path, monkeypatch):
    import shutil
    own = tmp_path / "vault-a" / ".wiki" / "wiki"
    own.parent.mkdir(parents=True)
    own.write_text("#!/bin/sh")
    other = tmp_path / "vault-b" / ".wiki" / "wiki"
    other.parent.mkdir(parents=True)
    other.write_text("#!/bin/sh")
    monkeypatch.setattr(health, "WIKI_DIR", own.parent)
    monkeypatch.setattr(shutil, "which", lambda _name: str(other))
    result = health.check_wiki_on_path()
    assert result.severity == "warning"
    assert "different vault" in result.message
    assert result.dispatch_args == ["install-shortcut"]
