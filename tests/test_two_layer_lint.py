"""M005-S02-T03: integration tests for `check_two_layer_pages` and
`check_action_item_syntax`.

Drives both lint functions against:
- the valid fixtures (tests/fixtures/two_layer/) — must surface ZERO issues
- the broken fixtures (tests/fixtures/two_layer_broken/) — must surface
  the expected issue codes per-file

Strategy: build a per-test temp `knowledge/` tree by symlinking the
fixture files into people/ or projects/ subdirs (driven by `type:`
frontmatter), then monkeypatch `lint.KNOWLEDGE_DIR` and run the checks.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

import lint

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_DIR = FIXTURES_DIR / "two_layer"
BROKEN_DIR = FIXTURES_DIR / "two_layer_broken"


def _build_knowledge(tmp_path: Path, sources: list[Path]) -> Path:
    """Materialise a fake knowledge/ tree from fixture sources.

    Files are filed into knowledge/people/ or knowledge/projects/ based on
    their frontmatter `type:` field. README.md files are skipped.
    """
    knowledge = tmp_path / "knowledge"
    (knowledge / "people").mkdir(parents=True)
    (knowledge / "projects").mkdir(parents=True)
    for src in sources:
        if src.name == "README.md":
            continue
        text = src.read_text(encoding="utf-8")
        match = re.search(r"^type:\s*(\w+)", text, re.MULTILINE)
        if not match:
            continue
        type_value = match.group(1)
        if type_value == "person":
            dest = knowledge / "people" / src.name
        elif type_value == "project":
            dest = knowledge / "projects" / src.name
        else:
            continue
        shutil.copy(src, dest)
    return knowledge


@pytest.fixture
def with_knowledge(tmp_path, monkeypatch):
    def _setup(sources: list[Path]) -> Path:
        knowledge = _build_knowledge(tmp_path, sources)
        monkeypatch.setattr(lint, "KNOWLEDGE_DIR", knowledge)
        return knowledge
    return _setup


# ── valid fixtures: zero issues ────────────────────────────────────


def test_valid_fixtures_have_no_two_layer_issues(with_knowledge):
    with_knowledge(sorted(VALID_DIR.glob("*.md")))
    issues = lint.check_two_layer_pages()
    assert issues == [], f"Expected no issues, got: {issues}"


def test_valid_fixtures_have_no_action_item_syntax_issues(with_knowledge):
    with_knowledge(sorted(VALID_DIR.glob("*.md")))
    issues = lint.check_action_item_syntax()
    assert issues == [], f"Expected no issues, got: {issues}"


# ── broken fixtures: expected issue codes per file ────────────────


def _codes_for_file(issues: list[dict], rel: str) -> set[str]:
    return {i["check"] for i in issues if i["file"] == rel}


def test_missing_state_surfaces_correct_code(with_knowledge):
    with_knowledge([BROKEN_DIR / "missing_state.md"])
    issues = lint.check_two_layer_pages()
    codes = _codes_for_file(issues, "people/missing_state.md")
    assert "two_layer_missing_state" in codes


def test_missing_separator_surfaces_correct_code(with_knowledge):
    with_knowledge([BROKEN_DIR / "missing_separator.md"])
    issues = lint.check_two_layer_pages()
    codes = _codes_for_file(issues, "people/missing_separator.md")
    assert "two_layer_missing_body_separator" in codes


def test_missing_timeline_surfaces_correct_code(with_knowledge):
    with_knowledge([BROKEN_DIR / "missing_timeline.md"])
    issues = lint.check_two_layer_pages()
    codes = _codes_for_file(issues, "projects/missing_timeline.md")
    assert "two_layer_missing_timeline" in codes


def test_timeline_out_of_order_surfaces_correct_code(with_knowledge):
    with_knowledge([BROKEN_DIR / "timeline_out_of_order.md"])
    issues = lint.check_two_layer_pages()
    codes = _codes_for_file(issues, "people/timeline_out_of_order.md")
    assert "timeline_not_reverse_chronological" in codes


def test_action_item_no_checkbox_surfaces_correct_code(with_knowledge):
    with_knowledge([BROKEN_DIR / "action_item_no_checkbox.md"])
    issues = lint.check_two_layer_pages()
    codes = _codes_for_file(issues, "people/action_item_no_checkbox.md")
    assert "action_items_malformed" in codes


def test_malformed_action_items_surfaces_all_three_codes(with_knowledge):
    with_knowledge([BROKEN_DIR / "malformed_action_items.md"])
    issues = lint.check_action_item_syntax()
    codes = _codes_for_file(issues, "people/malformed_action_items.md")
    assert "action_item_invalid_due_date" in codes
    assert "action_item_malformed_priority" in codes
    assert "action_item_empty_recurrence" in codes
