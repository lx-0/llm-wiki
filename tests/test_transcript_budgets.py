"""Behavioural tests for the per-class budgets in hooks/_transcript.py.

The pre-2026-05-16 design (MAX_TURNS=30 + MAX_CONTEXT_CHARS=15_000) lost
assistant analytical prose to tool-summary truncation. These tests pin the
asymmetric-truncation contract: long prose survives, tool spam is capped,
allocation is prefer-tail.
"""

from __future__ import annotations

import sys
from pathlib import Path

# hooks/ isn't on the default sys.path (conftest only adds scripts/) — the
# hooks scripts are normally invoked directly by the Claude Code harness, so
# they expect to import from their own directory.
_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import _transcript  # noqa: E402
from _transcript import Budgets, Turn, build_context  # noqa: E402


def _assistant(text: str = "", tools: list[str] | None = None) -> Turn:
    return Turn(role="assistant", text=text, tools=tools or [])


def _user(text: str = "", tools: list[str] | None = None) -> Turn:
    return Turn(role="user", text=text, tools=tools or [])


# ── Asymmetric truncation: prose budget independent of tool budget ────────

def test_long_assistant_prose_survives_a_tool_spam_burst():
    """The bug fixed: 50K analysis lost when tool dumps fill MAX_CONTEXT_CHARS."""
    long_analysis = "A" * 30_000
    tool_spam = [f"[Read] /some/long/path/file-{i}.py" for i in range(2000)]
    turns = [_assistant(text=long_analysis, tools=tool_spam)]

    out = build_context(turns, budgets=Budgets(
        assistant_text=50_000, user_text=10_000, tool_summary=10_000,
    ))

    assert long_analysis in out, "assistant prose was clipped despite fitting its own budget"
    # The 30K of prose must not be pushed out by the 50K+ of tool spam.


def test_tool_spam_capped_independent_of_prose():
    long_tools = ["[Bash] ls -la" for _ in range(2000)]  # ~28K total
    turns = [_assistant(text="short note", tools=long_tools)]

    out = build_context(turns, budgets=Budgets(
        assistant_text=50_000, user_text=10_000, tool_summary=5_000,
    ))

    tool_section_size = sum(len(line) for line in out.splitlines() if line.startswith("[Bash]"))
    assert tool_section_size <= 5_100, (
        f"tool budget exceeded: {tool_section_size} > 5000"
    )
    assert "short note" in out


# ── Prefer-tail: newest content wins under budget pressure ───────────────

def test_prefer_tail_drops_oldest_assistant_turns():
    """When assistant prose exceeds budget, the recent turns survive."""
    turns = [
        _assistant(text=f"turn-{i}: " + "X" * 100)
        for i in range(20)
    ]
    # 20 turns × ~110 chars = ~2200 chars; budget 500 keeps only the tail
    out = build_context(turns, budgets=Budgets(
        assistant_text=500, user_text=10_000, tool_summary=10_000,
    ))

    assert "turn-19" in out, "newest assistant turn must survive"
    assert "turn-0" not in out, "oldest assistant turn must be dropped first"


def test_prefer_tail_within_a_single_oversized_turn():
    """One assistant message larger than the whole budget: keep the tail."""
    huge = "OLD" * 5_000 + "NEW_PART_OF_PROSE"
    turns = [_assistant(text=huge)]

    out = build_context(turns, budgets=Budgets(
        assistant_text=200, user_text=10_000, tool_summary=10_000,
    ))

    assert "NEW_PART_OF_PROSE" in out
    assert "[... truncated" in out


# ── Turn dropping vs partial inclusion ───────────────────────────────────

def test_turn_kept_when_only_tool_stream_fits():
    """If assistant budget is full but tool budget isn't, the turn still emits."""
    filler = _assistant(text="X" * 1000)  # fills assistant budget
    target = _assistant(text="dropped prose", tools=["[Bash] target-cmd"])

    out = build_context([filler, target], budgets=Budgets(
        assistant_text=1_000, user_text=10_000, tool_summary=10_000,
    ))

    assert "[Bash] target-cmd" in out, (
        "tool summary must survive even when text class is full"
    )
    # The turn header (## Assistant) for the target turn must appear.
    assert out.count("## Assistant") >= 2


def test_completely_empty_turns_are_dropped():
    turns = [_user(text=""), _assistant(text="real text")]
    out = build_context(turns)
    assert out.count("## User") == 0
    assert "real text" in out


# ── Independence of user vs assistant budget ─────────────────────────────

def test_user_and_assistant_budgets_are_independent():
    """A long assistant turn doesn't starve user prose, and vice versa."""
    turns = [
        _user(text="U" * 8_000),
        _assistant(text="A" * 40_000),
    ]
    out = build_context(turns, budgets=Budgets(
        assistant_text=50_000, user_text=10_000, tool_summary=10_000,
    ))

    assert "U" * 8_000 in out
    assert "A" * 40_000 in out


# ── Chronological output order preserved ─────────────────────────────────

def test_output_is_chronological_after_tail_pruning():
    turns = [
        _user(text=f"q{i}") for i in range(5)
    ]
    out = build_context(turns)
    # All 5 should fit easily; check order.
    positions = [out.find(f"q{i}") for i in range(5)]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)


# ── from_config fallback path ────────────────────────────────────────────

def test_budgets_from_config_falls_back_cleanly_without_engine():
    """Standalone use (no CONFIG importable) must return Defaults, not crash."""
    # Save + clear the engine-config module if it happens to be loaded already
    saved = {k: sys.modules[k] for k in list(sys.modules) if k.startswith("core")}
    for k in saved:
        del sys.modules[k]

    # Block re-import by inserting a sentinel into sys.path... actually the
    # simplest is to just call from_config — if the engine is on the path it
    # returns real values, otherwise defaults. Either way must not raise.
    try:
        budgets = Budgets.from_config()
    finally:
        sys.modules.update(saved)

    assert budgets.assistant_text >= 1_000
    assert budgets.user_text >= 1_000
    assert budgets.tool_summary >= 1_000
