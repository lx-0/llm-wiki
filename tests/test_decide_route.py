"""M026-S02-T01: decide_route — the pure routing decision.

Table-tests the route selection + the substrate→model/max_turns precedence ladder
with no SDK / state / filesystem mocking. Paths are relative (not under ROOT_DIR)
so infer_compile_role's location lookup falls back to path.parts.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _route(content: str, path: str = "raw/notes/x.md", force: bool = False):
    from compile_stages.route import decide_route

    return decide_route(Path(path), content, force=force)


# ── terminal skip/index/stub routes ──────────────────────────────────

def test_empty_body_skips():
    from compile_stages.route import Skip

    r = _route("   \n  ")
    assert isinstance(r, Skip)
    assert r.reason == "empty"


def test_final_only_skips():
    from compile_stages.route import Skip

    r = _route("---\ncompile_role: final-only\n---\nbody")
    assert isinstance(r, Skip)
    assert r.reason == "compile_role_final_only"


def test_source_and_final_is_index_only():
    from compile_stages.route import IndexOnly

    content = (
        "---\ncompile_role: source-and-final\ntitle: My Strategy\n---\n"
        "see [[foo]] and [[bar]]"
    )
    r = _route(content)
    assert isinstance(r, IndexOnly)
    assert r.title == "My Strategy"
    assert set(r.wikilinks) >= {"foo", "bar"}


def test_source_and_final_title_falls_back_to_stem():
    from compile_stages.route import IndexOnly

    r = _route("---\ncompile_role: source-and-final\n---\nno title", path="raw/notes/my-doc.md")
    assert isinstance(r, IndexOnly)
    assert r.title == "My Doc"


def test_skip_list_type_skips_and_force_bypasses(monkeypatch):
    from core.config import CONFIG

    from compile_stages.route import Compile, Skip

    monkeypatch.setattr(CONFIG.limits, "compile_skip_substrate_types", ("calendar-rollup",))
    content = "---\ntype: calendar-rollup\n---\nstuff"
    assert isinstance(_route(content), Skip)
    assert isinstance(_route(content, force=True), Compile)  # force bypasses skip-list


def test_folder_index_default_skips_but_folder_answers_compile():
    """M027-S02-T03 carry-constraint: index = compile-skip (via the DEFAULT
    skip-list, no monkeypatch), `raw/notes/folder/` answers = compile SOURCES."""
    from compile_stages.route import Compile, Skip

    digest = "---\ntype: folder-index\nroot_id: nas-docs\n---\n## Tree\n- `x.txt`"
    r = _route(digest, path="raw/index/nas-docs.md")
    assert isinstance(r, Skip)
    assert r.reason == "substrate_type_excluded_folder-index"

    answer = "---\ntype: note\nkind: folder-deep-scan\n---\nDistilled answer body."
    assert isinstance(
        _route(answer, path="raw/notes/folder/answer-tax-2025.md"), Compile
    )


def test_health_rollup_stub_is_healthstub_but_prose_compiles():
    from compile_stages.route import Compile, HealthStub

    stub = (
        "---\ntype: health-rollup\n---\n# Health — 2026-05-20\n"
        "(Add observations below as needed.)"
    )
    assert isinstance(_route(stub), HealthStub)
    prose = "---\ntype: health-rollup\n---\n# Health — 2026-05-20\nFelt great after a long run."
    assert isinstance(_route(prose), Compile)


# ── Compile route + dispatch precedence ──────────────────────────────

def test_plain_note_uses_default_dispatch():
    from core.config import CONFIG

    from compile_stages.route import Compile

    r = _route("---\ntype: random-unmapped\n---\nbody text")
    assert isinstance(r, Compile)
    assert r.metadata.substrate_prompt == "compile_default"
    assert r.metadata.max_turns == CONFIG.limits.compile_max_turns
    assert r.metadata.model_id == "claude-haiku-4-5-20251001"
    assert r.metadata.substrate_type == "random-unmapped"


def test_calendar_rollup_dispatch():
    from compile_stages.route import Compile

    r = _route("---\ntype: calendar-rollup\n---\nmeetings")
    assert isinstance(r, Compile)
    assert r.metadata.substrate_prompt == "compile_calendar"
    assert r.metadata.model_id == "claude-haiku-4-5-20251001"
    assert r.metadata.max_turns == 12


def test_transcript_dispatch_routes_to_compile_main():
    """Issue #1: jamie/gmeet/youtube transcripts (type: transcript) must hit
    compile_main — the rich dialog prompt that owns person-stub creation +
    State/Timeline + Action-Item routing — not the lean compile_default that
    explicitly refuses person/project state work."""
    from compile_stages.route import Compile

    content = (
        "---\ntype: transcript\nsource: jamie\n"
        "participants:\n  - name: Alice\n  - name: Bob\n---\n"
        "Alice: shipping Friday.\nBob: I'll review the PR."
    )
    r = _route(content, path="raw/transcripts/jamie/2026-05-24-standup.md")
    assert isinstance(r, Compile)
    assert r.metadata.substrate_prompt == "compile_main"
    assert r.metadata.model_id == "claude-haiku-4-5-20251001"
    assert r.metadata.max_turns == 60
    assert r.metadata.substrate_type == "transcript"


def test_path_fallback_screenshot_batch():
    from compile_stages.route import Compile

    r = _route("no frontmatter here", path="raw/notes/screenshots/screenshots-2026.md")
    assert isinstance(r, Compile)
    assert r.metadata.substrate_prompt == "compile_screenshots"


def test_path_fallback_legacy_transcript():
    """Issue #1: legacy transcripts under raw/transcripts/ without a `type:`
    frontmatter still route to compile_main via the path fallback."""
    from compile_stages.route import Compile

    r = _route("Alice: hi\nBob: hey", path="raw/transcripts/gmeet/2026-old-meeting.md")
    assert isinstance(r, Compile)
    assert r.metadata.substrate_prompt == "compile_main"


def test_compile_carries_single_classification():
    from compile_stages.route import Compile

    r = _route("---\ntype: random-unmapped\n---\njust one block")
    assert isinstance(r, Compile)
    assert r.classification.kind == "single"


def test_size_escalation_when_dispatch_model_unset(monkeypatch):
    """Precedence ladder: when a dispatch entry has model=None, a large source
    escalates to the long-context model. (Currently dead for real data — every
    SUBSTRATE_PROMPTS entry pins haiku — so exercised via a patched dispatch.)"""
    from core.config import CONFIG

    from compile_stages import route
    from compile_stages.route import Compile

    monkeypatch.setattr(route, "_DEFAULT_DISPATCH", ("compile_default", 12, None))
    big = "---\ntype: unmapped-big\n---\n" + ("x " * (CONFIG.limits.compile_large_source_chars))
    r = _route(big)
    assert isinstance(r, Compile)
    expected = CONFIG.models.compile_large_source_model or CONFIG.models.compile_model
    assert r.metadata.model_id == expected
