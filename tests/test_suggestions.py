"""Tests for `scripts/suggestions/` — producer email-gating + cli helpers.

Producer `maybe_generate_suggestions` is SDK-bound (Claude Agent SDK
streaming call), so we test the pure pre-checks (`_is_email_source`) and
the early-return path without touching the network. CLI helpers
(`load_suggestion`, `save_suggestion`, `_resolve`) are pure-ish — we
exercise the YAML round-trip + the resolver's name/stem/substring chain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ── producer._is_email_source ───────────────────────────────────────


@pytest.mark.parametrize("path,expected", [
    ("raw/notes/email/work-2026-05-13.md", True),
    ("raw/notes/email/account-2026-05-13.md", True),  # generic email path
    ("raw/notes/thunderbird/overview.md", True),       # legacy thunderbird substrate path
    ("raw/notes/EMAIL/Capitals.md", True),             # case-insensitive
    ("raw/articles/news.md", False),
    ("daily/2026-05-13.md", False),
    ("raw/notes/screenshots/screenshots-x.md", False),
    ("raw/transcripts/jamie/x.md", False),
    ("", False),
])
def test_is_email_source(path: str, expected: bool) -> None:
    from suggestions.producer import _is_email_source
    assert _is_email_source(path) == expected


# ── producer early-return when not an email source ─────────────────


def test_maybe_generate_suggestions_skips_non_email_source(tmp_path, monkeypatch):
    """The function should short-circuit before any SDK / disk side effects."""
    from suggestions import producer
    import asyncio

    # Stub anything that would fire if the gate were broken.
    monkeypatch.setattr(
        producer,
        "render",
        lambda *a, **kw: pytest.fail("render() should not be called for non-email source"),
    )

    # Build a non-email source path under ROOT_DIR.
    monkeypatch.setattr(producer, "ROOT_DIR", tmp_path)
    src = tmp_path / "daily" / "2026-05-13.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("content", encoding="utf-8")

    # Should return None without raising or rendering.
    asyncio.run(producer.maybe_generate_suggestions(src, dry_run=False))


def test_maybe_generate_suggestions_dry_run_for_email_source(tmp_path, monkeypatch):
    """Email source + dry_run=True → log only, no SDK call."""
    from suggestions import producer
    import asyncio

    monkeypatch.setattr(producer, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(producer, "RAW_SUGGESTIONS_DIR", tmp_path / "raw" / "suggestions")
    monkeypatch.setattr(
        producer,
        "render",
        lambda *a, **kw: pytest.fail("render() should not be called in dry-run"),
    )

    src = tmp_path / "raw" / "notes" / "email" / "account-2026-05-13.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("Subject: hi\nFrom: a@b.com\n", encoding="utf-8")

    asyncio.run(producer.maybe_generate_suggestions(src, dry_run=True))
    # Suggestions dir should not be created in dry-run
    assert not (tmp_path / "raw" / "suggestions").exists()


# ── cli.load_suggestion / save_suggestion: YAML round-trip ─────────


def test_load_suggestion_strips_frontmatter_fences(tmp_path):
    from suggestions import cli

    p = tmp_path / "suggestion-test.md"
    p.write_text(
        "---\n"
        "type: optimization-suggestion\n"
        "category: email-filter\n"
        "actions:\n"
        "  - type: imap-move\n"
        "    status: pending\n"
        "---\n",
        encoding="utf-8",
    )

    data = cli.load_suggestion(p)
    assert data["type"] == "optimization-suggestion"
    assert data["category"] == "email-filter"
    assert len(data["actions"]) == 1
    assert data["actions"][0]["status"] == "pending"


def test_save_suggestion_round_trip(tmp_path):
    from suggestions import cli

    src_payload = {
        "type": "optimization-suggestion",
        "category": "email-filter",
        "actions": [
            {"type": "imap-move", "status": "pending", "target": "Newsletter"},
            {"type": "create-rule", "status": "rejected", "target": "Spam"},
        ],
    }
    p = tmp_path / "suggestion-roundtrip.md"
    cli.save_suggestion(p, src_payload)
    reloaded = cli.load_suggestion(p)
    assert reloaded == src_payload


def test_save_changes_action_status_persists(tmp_path):
    """The approve/reject flow mutates `action['status']` and writes back."""
    from suggestions import cli

    p = tmp_path / "suggestion-status.md"
    payload = {
        "type": "optimization-suggestion",
        "actions": [{"type": "imap-move", "status": "pending"}],
    }
    cli.save_suggestion(p, payload)

    data = cli.load_suggestion(p)
    data["actions"][0]["status"] = "approved"
    cli.save_suggestion(p, data)

    reloaded = cli.load_suggestion(p)
    assert reloaded["actions"][0]["status"] == "approved"


# ── cli._resolve: name / stem / substring chain ────────────────────


def test_resolve_matches_filename(tmp_path, monkeypatch):
    from suggestions import cli

    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)
    files = [tmp_path / "a.md", tmp_path / "b-test.md", tmp_path / "c.md"]
    for f in files:
        f.write_text("---\n---\n", encoding="utf-8")

    assert cli._resolve("b-test.md", files) == tmp_path / "b-test.md"
    assert cli._resolve("b-test", files) == tmp_path / "b-test.md"  # stem match
    assert cli._resolve("test", files) == tmp_path / "b-test.md"    # substring match


def test_resolve_returns_none_for_no_match(tmp_path, monkeypatch, capsys):
    from suggestions import cli

    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)
    files = [tmp_path / "a.md"]
    for f in files:
        f.write_text("---\n---\n", encoding="utf-8")

    result = cli._resolve("nonexistent", files)
    assert result is None
    captured = capsys.readouterr()
    assert "Not found: nonexistent" in captured.out
