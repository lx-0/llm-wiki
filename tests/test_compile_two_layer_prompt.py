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
