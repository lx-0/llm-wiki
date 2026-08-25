"""Stale-session env sanitizing before SDK spawns (M031-S01).

Root cause, live-proven 2026-08-25 (T3/T5 discriminating experiment on lxw):
SessionEnd-hook children inherit CLAUDE_CODE_SSE_PORT / MESSAGING_SOCKET of
the DYING parent session; the bundled CLI contacts the dead endpoint and exits
1 with empty stderr — the entire flush-extract outage since 2026-08-14 (the
day the host Claude Code update introduced these env vars). Input-independent:
39-byte contexts failed identically. Fix = strip the session-wiring class in
the ONE SDK harness before any spawn.
"""
from __future__ import annotations

from core.sdk_helpers import sanitize_stale_session_env


def _env() -> dict[str, str]:
    return {
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SSE_PORT": "12345",
        "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_SESSION_ID": "abc",
        "CLAUDE_PID": "999",
        "CLAUDE_EFFORT": "high",
        "CLAUDE_INVOKED_BY": "flush",  # ENGINE-owned marker — must survive
        "ANTHROPIC_API_KEY": "sk-keep",  # auth — must survive
        "PATH": "/usr/bin",
        "HOME": "/Users/x",
    }


def test_strips_session_wiring_class() -> None:
    env = _env()
    removed = sanitize_stale_session_env(env)
    assert "CLAUDECODE" not in env
    assert not any(k.startswith("CLAUDE_CODE_") for k in env)
    assert "CLAUDE_PID" not in env and "CLAUDE_EFFORT" not in env
    assert sorted(removed) == [
        "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SSE_PORT", "CLAUDE_EFFORT",
        "CLAUDE_PID",
    ]


def test_keeps_engine_marker_auth_and_unrelated() -> None:
    env = _env()
    sanitize_stale_session_env(env)
    assert env["CLAUDE_INVOKED_BY"] == "flush"
    assert env["ANTHROPIC_API_KEY"] == "sk-keep"
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/Users/x"


def test_idempotent_and_clean_env_noop() -> None:
    env = {"PATH": "/usr/bin"}
    assert sanitize_stale_session_env(env) == []
    assert env == {"PATH": "/usr/bin"}
