"""docs/config.md + config.example.yaml drift gate (C05).

docs/config.md's key tables are generated from `core.config_schema`; these
tests fail whenever the committed docs or the shipped example drift from the
schema — the doc-rot class that previously accumulated 7+ stale defaults,
including the safety-relevant claim that `piggybacks.optimize_claude_md`
(the only piggyback writing outside the vault) ships enabled.

Regenerate after schema changes:  uv run python scripts/core/config_docs.py --write
"""

from __future__ import annotations

from pathlib import Path

from core import config_docs

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "config.md"
EXAMPLE = REPO_ROOT / "config.example.yaml"


def test_docs_config_md_is_current():
    existing = DOCS.read_text(encoding="utf-8")
    regenerated = config_docs.render_docs(existing)
    assert regenerated == existing, (
        "docs/config.md is stale relative to core/config_schema.py — run "
        "`uv run python scripts/core/config_docs.py --write` and commit the result"
    )


def test_config_example_yaml_in_sync_with_schema():
    problems = config_docs.check_example(EXAMPLE)
    assert problems == [], "config.example.yaml drifted from the schema:\n" + "\n".join(
        f"  - {p}" for p in problems
    )


def test_generated_tables_reflect_safety_truth():
    """Regression pins for the exact lies the hand-written doc accumulated."""
    tables = config_docs.generate_tables()
    # optimize_claude_md was shown enabled:true though force-disabled 2026-06-13.
    assert "| `piggybacks.optimize_claude_md` | `false` |" in tables
    # compile_model was shown as the retired claude-opus-4-7.
    assert '| `models.compile_model` | `"claude-opus-4-8"` |' in tables
    # curiosity_model was shown as gemma4:e4b — documented in the schema itself
    # as the schema-ignoring '6-week stillstand' pick.
    assert '| `models.curiosity_model` | `"llama3.1:8b"` |' in tables
    # dedup_window_seconds was shown as the pre-2026-07-14 default 60.
    assert "| `scheduling.dedup_window_seconds` | `900` |" in tables
    # Renamed-away piggyback keys must not resurface as documented keys.
    assert "`piggybacks.scan_screenshots`" not in tables
    assert "`piggybacks.follow_requests`" not in tables
    assert "`piggybacks.email_incremental`" not in tables


def test_meaning_extraction_is_sentence_aware():
    """First-sentence extraction tolerates common abbreviations and extends
    arc-label-only openers with the following sentence."""
    assert (
        config_docs._meaning(
            "Cap for the very large first thing (e.g. big runs) over there. Second sentence."
        )
        == "Cap for the very large first thing (e.g. big runs) over there."
    )
    # Short arc label alone would be meaningless — second sentence pulled in.
    assert config_docs._meaning("M014 dream-cycle. The real explanation here.") == (
        "M014 dream-cycle. The real explanation here."
    )
    assert config_docs._meaning("") == "—"
