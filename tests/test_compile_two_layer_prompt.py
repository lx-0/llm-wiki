"""M005-S01-T04 smoke test: the two-layer schema rule reaches the rendered
compile prompt unchanged.

Why pytest and not `compile.py --dry-run`: dry-run skips the LLM call but
never assembles + emits the prompt. To smoke-test the prompt as the LLM
would see it, the surgical path is calling `core.prompts.render` directly.

LLM-emission quality (does the model actually obey the rule?) is S03's
real-substrate canary deliverable, not this plumbing test.
"""
from __future__ import annotations

from core.prompts import render


_DUMMY_VARS = {
    "agents_md": "",
    "facts_md": "",
    "index_md": "",
    "source_path": "raw/transcripts/jamie/test.md",
    "source_content": "dummy content",
    "today": "2026-05-15",
    "now": "2026-05-15T17:00:00Z",
}


def test_compile_prompt_contains_two_layer_schema() -> None:
    rendered = render("compile_main", **_DUMMY_VARS)
    # New Instruction 3 marker
    assert "Two-layer shape for `type: person|project`" in rendered
    # All four required section names appear (in the example block + rules)
    for header in ("## State", "## Action Items", "## Open Threads", "## Timeline"):
        assert header in rendered, f"missing section header in rendered prompt: {header}"
    # Obsidian-Tasks-plugin syntax is named explicitly
    assert "Obsidian-Tasks-plugin syntax" in rendered


def test_compile_prompt_includes_atomic_exception_for_other_types() -> None:
    rendered = render("compile_main", **_DUMMY_VARS)
    # Other types keep the existing atomic shape — explicit exception clause
    assert "do NOT emit the two-layer structure" in rendered


def test_compile_prompt_carries_entity_resolution_rule() -> None:
    """M005-S03-T02: the entity-resolution deepening (slugification +
    alias-fallback + disambiguation + stub-minimum) must reach the rendered
    prompt unchanged.
    """
    rendered = render("compile_main", **_DUMMY_VARS)
    assert "Resolving the Owner to an entity page" in rendered
    assert "Slugify the name" in rendered
    # Slug example
    assert "jane-doe" in rendered
    # Alias-fallback lookup
    assert "aliases:" in rendered
    # Disambiguation rule
    assert "Disambiguation" in rendered or "two pages match" in rendered
    # Stub-creation guard
    assert "Don't stub for one-off mentions" in rendered


def test_compile_prompt_carries_lifecycle_rules() -> None:
    """M005-S04-T01: lifecycle carry-forward + manual-[x] preservation must
    reach the rendered prompt unchanged.
    """
    rendered = render("compile_main", **_DUMMY_VARS)
    assert "Lifecycle: carry-forward and manual-check preservation" in rendered
    assert "Read first, rewrite second" in rendered
    assert "Carry forward unresolved Action Items" in rendered
    assert "Preserve manual `- [x]`" in rendered
    assert "Deduplicate by task-phrase similarity" in rendered
    assert "Stale-flag, don't auto-delete" in rendered or "stale?" in rendered


def test_compile_prompt_carries_resolution_rules() -> None:
    """M005-S04-T02: resolution-detection + demotion rules must reach the
    rendered prompt unchanged.
    """
    rendered = render("compile_main", **_DUMMY_VARS)
    assert "Resolution detection and demotion" in rendered
    # Sample resolution-signal phrases the prompt names
    assert "Sent the deck" in rendered
    # Demotion mechanic
    assert "REMOVE the `- [ ]` line" in rendered or "REMOVE the - [ ] line" in rendered
    assert "[resolved]" in rendered
    # Anti-false-positive guard
    assert "never demote based on hypothetical" in rendered
    # Confirmed-resolved special case
    assert "[resolved-manual+substrate]" in rendered


def test_compile_prompt_carries_commitment_extraction_rule() -> None:
    """M005-S03-T01: the meeting-substrate commitment-extraction rule (Task/
    Owner/Deadline/Context quartet + entity routing + Timeline citation) must
    reach the rendered prompt unchanged.
    """
    rendered = render("compile_main", **_DUMMY_VARS)
    # Section headline
    assert "Extracting commitments from meeting substrates" in rendered
    # Quartet markers
    for marker in ("**Task**", "**Owner**", "**Deadline**", "**Context**"):
        assert marker in rendered, f"missing commitment-quartet marker: {marker}"
    # Substrate scope (jamie + gmeet path patterns)
    assert "raw/transcripts/jamie/" in rendered
    assert "raw/transcripts/gmeet/" in rendered
    # Quality-bar / anti-hallucination clause
    assert "better to miss a fuzzy commitment than fabricate one" in rendered
