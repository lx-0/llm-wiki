"""Tests for `wiki correct apply` — the agentic fact-propagation path.

M028-S01: `apply()` must run sandboxed like `reconcile_fact()` — no Bash, a
PreToolUse path-scope hook, `permission_mode="default"`, and a config-knob
turn bound. The agent annotates; it can no longer shell out or delete.
"""

from __future__ import annotations


def test_apply_options_sandboxed() -> None:
    """`_apply_agent_options` returns a non-destructive, path-scoped config.

    Regression guard for issue #5: the wide-open `apply()` (Bash +
    acceptEdits + hardcoded 50 turns, no hook) deleted 17 articles. The
    sandboxed options make destruction structurally impossible.
    """
    from facts import correct_apply
    from core.config import CONFIG
    from core.sdk_helpers import StderrCapture

    opts = correct_apply._apply_agent_options(StderrCapture())

    # Bash is gone — the agent cannot `rm`/`git mv`.
    assert "Bash" not in opts.allowed_tools
    assert set(opts.allowed_tools) == {"Read", "Glob", "Grep", "Write", "Edit"}

    # Not acceptEdits — writes go through the hook.
    assert opts.permission_mode == "default"

    # Turn bound is a config knob, not a magic number.
    assert opts.max_turns == CONFIG.limits.correct_apply_max_turns

    # A PreToolUse Write|Edit hook is wired (path-scope).
    assert "PreToolUse" in (opts.hooks or {})
    assert opts.hooks["PreToolUse"], "PreToolUse hook list must be non-empty"


def _render_apply_prompt(deletion_allowed: str = "false") -> str:
    from core.prompts import render

    return render(
        "correct_apply",
        fact_content="---\nstatus: negation\n---\nWe did NOT win X.",
        fact_path="knowledge/facts/x.md",
        slug="x",
        today="2026-06-13",
        now="2026-06-13T12:00:00",
        deletion_allowed=deletion_allowed,
    )


def test_apply_prompt_supersedes_by_default() -> None:
    """M028-S01-T03: the negation branch annotates, it does not delete."""
    p = _render_apply_prompt()
    assert "status: superseded" in p
    assert "superseded_by" in p
    assert "outdated_since" in p
    # The load-bearing rule, verbatim.
    assert "outdated != false" in p
    # No-shell / engine-disposes contract.
    assert "no shell" in p.lower()


def test_apply_prompt_has_json_proposal_contract() -> None:
    """The agent emits a machine-readable `## Proposed actions` JSON block."""
    p = _render_apply_prompt()
    assert "## Proposed actions" in p
    for key in ("superseded", "renamed", "deleted"):
        assert f'"{key}"' in p


def test_apply_prompt_renders_deletion_gate() -> None:
    """`${deletion_allowed}` is threaded so S02 can gate deletion nomination."""
    assert "Deletion permitted: false" in _render_apply_prompt("false")
    assert "Deletion permitted: true" in _render_apply_prompt("true")
