"""M005-S04-T03: plumbing tests for the resolution-demotion lifecycle path.

Validates the BEFORE / AFTER fixture pair shape and that the rendered
compile prompt for the AFTER substrate carries the resolution-detection
rules from T02. LLM-emission validation is operator-canary work.
"""
from __future__ import annotations

from pathlib import Path

from core.prompts import render

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "lifecycle"
BEFORE_PATH = FIXTURES_DIR / "jane-doe-before.md"
AFTER_PATH = FIXTURES_DIR / "jamie-followup-after.md"


def test_before_fixture_has_expected_open_commitment() -> None:
    """The BEFORE entity page must carry the open commitment shape that the
    lifecycle rule expects to find on Read-first."""
    body = BEFORE_PATH.read_text(encoding="utf-8")
    assert "- [ ] Send the Q3 deck 📅 2026-04-22" in body
    assert "- [ ] Follow up on Bob intro" in body
    assert "Waiting on Hetzner infra-capacity decision" in body
    # Two-layer shape intact
    assert "## State" in body
    assert "## Action Items" in body
    assert "## Open Threads" in body
    assert "## Timeline" in body


def test_after_substrate_carries_resolution_signal() -> None:
    """The AFTER substrate must contain a resolution signal in a form
    matching the prompt's resolution-signal categories (past-tense first-
    person announcement of a previously-committed action)."""
    body = AFTER_PATH.read_text(encoding="utf-8")
    # The canonical resolution phrase
    assert "I sent the Q3 deck this morning" in body
    # The non-resolution phrase (Bob intro NOT done — should carry forward)
    assert "haven't done the intro yet" in body
    # The carry-forward Open Thread (Hetzner)
    assert "Nothing yet from them" in body


def test_rendered_prompt_for_after_substrate_carries_resolution_rules() -> None:
    body = AFTER_PATH.read_text(encoding="utf-8")
    rendered = render(
        "compile_main",
        agents_md="",
        facts_md="",
        index_md="",
        source_path="raw/transcripts/jamie/2026-04-22--followup-deck--xyz.md",
        source_content=body,
        today="2026-04-22",
        now="2026-04-22T11:00:00Z",
    )
    # Resolution-detection rule is in the prompt
    assert "Resolution detection and demotion" in rendered
    # Carry-forward rule is in the prompt (T01)
    assert "Carry forward unresolved Action Items" in rendered
    # The AFTER substrate body is interpolated unchanged
    assert "I sent the Q3 deck this morning" in rendered
    # The anti-FP guard
    assert "never demote based on hypothetical" in rendered
