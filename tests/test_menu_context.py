"""Tests for scripts/menu_context.py — the home-screen context probe.

The probes read vault state from `core.paths` module-level constants. We
monkeypatch those constants in the `menu_context` module itself (which
imported them with `from core.paths import …`) so each test runs against
an isolated tmp_path vault.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MENU_CONTEXT_PY = REPO_ROOT / "scripts" / "menu_context.py"


@pytest.fixture
def fake_vault(tmp_path, monkeypatch):
    """A tmp_path vault with empty subdirs the probes look for.

    Returns the tmp_path so each test can create its own state. Monkeypatches
    the `menu_context` module so all probes read from this vault.
    """
    import menu_context

    inbox = tmp_path / "inbox"
    raw = tmp_path / "raw"
    raw_requests = raw / "requests"
    raw_suggestions = raw / "suggestions"
    daily = tmp_path / "daily"
    daily_sessions = daily / "sessions"
    knowledge = tmp_path / "knowledge"
    people = knowledge / "people"
    projects = knowledge / "projects"
    areas = knowledge / "areas"
    reports = tmp_path / ".wiki" / "reports"
    state = tmp_path / ".wiki" / "state"
    for d in (inbox, raw_requests, raw_suggestions, daily_sessions,
              people, projects, areas, reports, state):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(menu_context, "INBOX_DIR", inbox)
    monkeypatch.setattr(menu_context, "RAW_DIR", raw)
    monkeypatch.setattr(menu_context, "RAW_REQUESTS_DIR", raw_requests)
    monkeypatch.setattr(menu_context, "RAW_SUGGESTIONS_DIR", raw_suggestions)
    monkeypatch.setattr(menu_context, "DAILY_DIR", daily)
    monkeypatch.setattr(menu_context, "PEOPLE_DIR", people)
    monkeypatch.setattr(menu_context, "PROJECTS_DIR", projects)
    monkeypatch.setattr(menu_context, "AREAS_DIR", areas)
    monkeypatch.setattr(menu_context, "REPORTS_DIR", reports)
    monkeypatch.setattr(menu_context, "STATE_FILE", state / "state.json")
    monkeypatch.setattr(menu_context, "KNOWLEDGE_DIR", knowledge)
    return tmp_path


# ── Per-probe tests ─────────────────────────────────────────────────


def test_inbox_counts_files_only_not_subdirs(fake_vault):
    import menu_context

    (fake_vault / "inbox" / "a.md").write_text("x")
    (fake_vault / "inbox" / "b.html").write_text("x")
    (fake_vault / "inbox" / "subdir").mkdir()
    assert menu_context.probe_inbox() == 2


def test_inbox_empty_returns_zero(fake_vault):
    import menu_context

    assert menu_context.probe_inbox() == 0


def test_compile_changed_when_no_state_counts_all_sources(fake_vault):
    import menu_context

    (fake_vault / "raw" / "a.md").write_text("x")
    (fake_vault / "raw" / "b.md").write_text("x")
    (fake_vault / "daily" / "c.md").write_text("x")
    assert menu_context.probe_compile_changed() == 3


def test_compile_changed_with_state_counts_only_newer(fake_vault):
    import menu_context

    old = fake_vault / "raw" / "old.md"
    old.write_text("x")
    import os
    # Backdate the source so it's older than last_compile.
    ten_minutes_ago = datetime.now().timestamp() - 600
    os.utime(old, (ten_minutes_ago, ten_minutes_ago))
    last_compile = datetime.now().replace(microsecond=0).isoformat()
    menu_context.STATE_FILE.write_text(json.dumps({"last_compile": last_compile}))

    new = fake_vault / "raw" / "new.md"
    new.write_text("x")
    assert menu_context.probe_compile_changed() == 1


def test_curiosity_probes_split_folder_from_email(fake_vault):
    """The home-screen suggestion splits high-value folder-deep-scans from
    the email pile so they aren't buried; done/rejected excluded."""
    import menu_context

    requests = fake_vault / "raw" / "requests"
    (requests / "request-a.json").write_text(
        json.dumps({"type": "email-deep-scan", "status": "pending"}))
    (requests / "request-b.json").write_text(
        json.dumps({"type": "email-deep-scan", "status": "in_progress"}))
    (requests / "request-c.json").write_text(
        json.dumps({"type": "folder-deep-scan", "status": "pending"}))
    (requests / "request-d.json").write_text(
        json.dumps({"type": "folder-deep-scan", "status": "done"}))
    (requests / "request-e.json").write_text(
        json.dumps({"type": "email-deep-scan", "status": "rejected"}))
    (requests / "request-bad.json").write_text("not json")

    assert menu_context.probe_folder_curiosity_pending() == 1  # pending folder only
    assert menu_context.probe_curiosity_pending() == 2         # non-terminal email
    assert menu_context._count_pending_requests() == 3         # all pending, any type


def test_suggestions_counts_approved_lines(fake_vault):
    import menu_context

    s = fake_vault / "raw" / "suggestions" / "test.yaml"
    s.write_text(
        "---\nactions:\n"
        "  - type: foo\n    status: approved\n"
        "  - type: bar\n    status: pending\n"
        "  - type: baz\n    status: approved\n"
        "---\n"
    )
    assert menu_context.probe_suggestions_approved() == 2


def test_dream_overdue_counts_missing_and_old(fake_vault, monkeypatch):
    import menu_context

    monkeypatch.setattr(menu_context, "_read_dream_cooldown_days", lambda: 7)

    # No frontmatter → counts as overdue.
    (fake_vault / "knowledge" / "people" / "no-fm.md").write_text("# body")

    # Old frontmatter → counts as overdue.
    old = datetime.now(timezone.utc) - timedelta(days=30)
    (fake_vault / "knowledge" / "people" / "old.md").write_text(
        f"---\nlast_synthesized_at: {old.isoformat()}\n---\n# body"
    )

    # Recent → does NOT count.
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    (fake_vault / "knowledge" / "projects" / "fresh.md").write_text(
        f"---\nlast_synthesized_at: {recent.isoformat()}\n---\n# body"
    )

    assert menu_context.probe_dream_overdue() == 2


def test_flush_missing_returns_1_when_no_session_today(fake_vault):
    import menu_context

    assert menu_context.probe_flush_missing() == 1


def test_flush_missing_returns_0_when_today_present(fake_vault):
    import menu_context

    today = datetime.now().strftime("%Y-%m-%d")
    (fake_vault / "daily" / "sessions" / f"{today}.md").write_text("x")
    assert menu_context.probe_flush_missing() == 0


def test_lint_stale_with_no_reports_returns_1(fake_vault, monkeypatch):
    import menu_context

    # KNOWLEDGE_DIR isn't monkeypatched on the module top-level — the probe
    # imports it lazily. Point it at our fake vault for this test.
    monkeypatch.setattr(
        "core.paths.KNOWLEDGE_DIR", fake_vault / "knowledge", raising=False
    )
    assert menu_context.probe_lint_stale() == 1


# ── End-to-end main() + CLI invocation ──────────────────────────────


def test_build_suggestions_returns_only_nonzero_counts_sorted(fake_vault):
    import menu_context

    # Only inbox has content.
    (fake_vault / "inbox" / "a.md").write_text("x")
    # Don't trigger compile (state with no changed sources).
    last_compile = datetime.now().replace(microsecond=0).isoformat()
    menu_context.STATE_FILE.write_text(json.dumps({"last_compile": last_compile}))
    # Today's flush exists.
    today = datetime.now().strftime("%Y-%m-%d")
    (fake_vault / "daily" / "sessions" / f"{today}.md").write_text("x")
    # Lint cache exists, newer than knowledge.
    (fake_vault / ".wiki" / "reports" / "lint-2026-05-17.md").write_text("ok")

    results = menu_context.build_suggestions()
    # Only inbox should remain non-zero.
    keys = [r["cmd"] for r in results]
    assert "process-inbox" in keys
    # All entries have the right schema.
    for r in results:
        assert set(r.keys()) == {"count", "label", "cmd", "priority", "key"}
        assert r["count"] > 0
    # Sorted by ascending priority + auto-numbered keys.
    priorities = [r["priority"] for r in results]
    assert priorities == sorted(priorities)
    assert [r["key"] for r in results] == [str(i + 1) for i in range(len(results))]


def test_cli_emits_valid_json_object():
    """End-to-end: subprocess call returns a parseable {status, suggestions}."""
    proc = subprocess.run(
        [sys.executable, str(MENU_CONTEXT_PY)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert isinstance(data, dict)
    assert set(data.keys()) == {"status", "suggestions"}
    assert isinstance(data["status"], dict)
    assert isinstance(data["suggestions"], list)


# ── Status one-liner probes ─────────────────────────────────────────


def test_articles_counts_md_excluding_index_and_log(fake_vault):
    import menu_context

    (fake_vault / "knowledge" / "concepts").mkdir(parents=True, exist_ok=True)
    (fake_vault / "knowledge" / "concepts" / "a.md").write_text("x")
    (fake_vault / "knowledge" / "concepts" / "b.md").write_text("x")
    (fake_vault / "knowledge" / "index.md").write_text("x")
    (fake_vault / "knowledge" / "log.md").write_text("x")
    assert menu_context.probe_articles() == 2


def test_last_compile_ago_humanizes_delta(fake_vault):
    import menu_context

    # 90 minutes ago.
    past = datetime.now() - timedelta(minutes=90)
    menu_context.STATE_FILE.write_text(json.dumps({"last_compile": past.isoformat()}))
    ago = menu_context.probe_last_compile_ago()
    assert ago == "1h"


def test_last_compile_ago_none_when_never_compiled(fake_vault):
    import menu_context

    assert menu_context.probe_last_compile_ago() is None


def test_build_status_returns_dict_with_articles_at_minimum(fake_vault):
    import menu_context

    (fake_vault / "knowledge" / "concepts").mkdir(parents=True, exist_ok=True)
    (fake_vault / "knowledge" / "concepts" / "a.md").write_text("x")
    status = menu_context.build_status()
    assert isinstance(status, dict)
    assert status.get("articles") == 1
