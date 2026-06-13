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
