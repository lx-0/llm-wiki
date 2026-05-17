"""Tests for core.google_oauth.resolve_client_file — per-account OAuth client precedence."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def claude_dir(tmp_path, monkeypatch):
    d = tmp_path / ".claude"
    d.mkdir()
    from core import google_oauth as go
    monkeypatch.setattr(go, "ROOT_DIR", tmp_path)
    return d


def test_per_account_wins_over_global(claude_dir):
    from core.google_oauth import resolve_client_file
    (claude_dir / "google-oauth-client.json").write_text("{}")
    per = claude_dir / "oauth-client-work.json"
    per.write_text("{}")
    assert resolve_client_file("work") == per


def test_global_wins_when_no_per_account(claude_dir):
    from core.google_oauth import resolve_client_file
    g = claude_dir / "google-oauth-client.json"
    g.write_text("{}")
    assert resolve_client_file("work") == g


def test_legacy_wins_when_neither_per_account_nor_global(claude_dir):
    from core.google_oauth import resolve_client_file
    legacy = claude_dir / "gmail-oauth-client.json"
    legacy.write_text("{}")
    assert resolve_client_file("work", integration_legacy=legacy) == legacy


def test_returns_per_account_path_when_nothing_exists(claude_dir):
    from core.google_oauth import resolve_client_file
    expected = claude_dir / "oauth-client-work.json"
    # nothing on disk; bootstrap's missing-file error should reference per-account
    assert resolve_client_file("work") == expected


def test_different_accounts_get_different_files(claude_dir):
    from core.google_oauth import resolve_client_file
    work = claude_dir / "oauth-client-work.json"
    home = claude_dir / "oauth-client-home.json"
    work.write_text("{}")
    home.write_text("{}")
    assert resolve_client_file("work") == work
    assert resolve_client_file("home") == home
    assert resolve_client_file("work") != resolve_client_file("home")


def test_per_account_isolation_global_unused_when_per_account_present(claude_dir):
    """The whole point: if an account has its own OAuth client file, the
    shared global is completely bypassed for that account — different
    accounts in different Cloud projects, no cross-account coupling."""
    from core.google_oauth import resolve_client_file
    (claude_dir / "google-oauth-client.json").write_text("shared")
    per = claude_dir / "oauth-client-private.json"
    per.write_text("private")
    chosen = resolve_client_file("private")
    assert chosen == per
    assert chosen.read_text() == "private"
