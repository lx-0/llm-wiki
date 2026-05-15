"""M005-S04-T04: plumbing tests for the manual-[x] preservation lifecycle path.

The BEFORE entity page has `- [x] Sign the contract` (operator-checked).
The AFTER substrate touches the page (an email from Bob) but does NOT
mention the contract. Validates that the rendered compile prompt carries
the preservation rule (T01) so a future canary run will preserve the [x].
"""
from __future__ import annotations

from pathlib import Path

from core.prompts import render

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "lifecycle"
BEFORE_PATH = FIXTURES_DIR / "bob-smith-before.md"
AFTER_PATH = FIXTURES_DIR / "email-touch-after.md"


def test_before_fixture_has_manual_checked_item() -> None:
    """BEFORE entity page must carry the manual `[x]` shape that T01's
    preservation rule expects to find."""
    body = BEFORE_PATH.read_text(encoding="utf-8")
    assert "- [x] Sign the contract" in body
    # Also has a parallel open item for contrast
    assert "- [ ] Schedule onboarding call 📅 2026-04-15" in body
    # Two-layer shape intact
    for header in ("## State", "## Action Items", "## Open Threads", "## Timeline"):
        assert header in body


def test_after_substrate_does_not_mention_contract() -> None:
    """AFTER substrate touches Bob's page but carries NO resolution signal
    for the [x] item. Plumbing assertion: nothing in the email body
    matches the contract task — preservation rule should not be tempted
    to demote."""
    body = AFTER_PATH.read_text(encoding="utf-8")
    # Substrate touches Bob — preservation context is real
    assert "Bob Smith" in body
    # But no contract / signing language
    assert "contract" not in body.lower().split("expected lifecycle")[0], \
        "AFTER substrate body must not mention 'contract' before the truth-set block"
    # A genuine new commitment IS present (operator's EOW response)
    assert "EOW" in body or "follow up" in body.lower()


def test_rendered_prompt_for_after_substrate_carries_preservation_rule() -> None:
    body = AFTER_PATH.read_text(encoding="utf-8")
    rendered = render(
        "compile_main",
        agents_md="",
        facts_md="",
        index_md="",
        source_path="raw/notes/email/personal-2026-04-10.md",
        source_content=body,
        today="2026-04-10",
        now="2026-04-10T09:00:00Z",
    )
    # Preservation rule (T01) is in the prompt
    assert "Preserve manual `- [x]`" in rendered
    # The substrate body is interpolated unchanged
    assert "dashboard view in our staging env shows stale" in rendered
    # Resolution detection is also in the prompt (so the LLM knows when to
    # demote vs. preserve — both rules coexist)
    assert "Resolution detection and demotion" in rendered
    # Anti-FP guard prevents the LLM from demoting on weak signals
    assert "never demote based on hypothetical" in rendered
