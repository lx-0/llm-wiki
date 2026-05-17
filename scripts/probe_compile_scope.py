"""Empirical verification of the compile-scope allowlist (commit 57fc0d4).

The fix shipped a path-scoped `allowed_tools` of
    ["Read", "Glob", "Grep", "Write(knowledge/**)", "Edit(knowledge/**)"]
plus `permission_mode="acceptEdits"` and `setting_sources=["project"]`.

Unverified assumption: the bundled Claude Code CLI parses
`Write(knowledge/**)` as a path-scoped permission rather than treating
the parenthesised suffix as an unknown tool name. If that's wrong, the
bare `Write` tool isn't in the allowlist, and EVERY Write/Edit gets
denied — including the inside-scope ones the compiler needs.

This probe runs two sequential SDK calls against a throwaway tmp vault:

  1. INSIDE-SCOPE — asks the agent to Write `inside.md` under `knowledge/`.
     Expected: file appears on disk (positive control).
  2. OUTSIDE-SCOPE — asks the agent to Write `outside.md` at vault root.
     Expected: file does NOT appear (path-scope rejected the call).

Outcomes:
  - Both as expected → fix verified. Commit message can drop "UNTESTED".
  - Inside fails too → pattern is interpreted as a bogus tool name; the
    allowlist denies ALL writes. Roll back or switch to denylist /
    `can_use_tool` callback. Compile would be broken in production.
  - Outside succeeds → path scope ignored; the injection surface is
    still open. Switch to `can_use_tool` callback (bulletproof Python-
    side gate, not subject to CLI parsing semantics).

Cost: ~$0.05-0.10 (two small Claude SDK calls). Run manually; not
wired into pytest.

Usage:
    uv run --project .wiki python scripts/probe_compile_scope.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    UserMessage,
    query,
)

# Mirror the production `allowed_tools` 1:1 — that's the whole point.
PRODUCTION_ALLOWED_TOOLS = [
    "Read", "Glob", "Grep",
    "Write(knowledge/**)",
    "Edit(knowledge/**)",
]

# Replacement allowlist for the can_use_tool probe — Write/Edit must NOT
# be in allowed_tools, otherwise the bundled CLI fast-paths them as
# "pre-approved" and never consults the callback. With Write/Edit absent,
# the CLI asks for permission per call → callback fires → callback decides.
CALLBACK_ALLOWED_TOOLS = ["Read", "Glob", "Grep"]


def make_knowledge_only_gate(vault: Path):
    """Build a can_use_tool callback that denies Write/Edit outside
    `<vault>/knowledge/`. Mirrors what we'd ship in compile.py."""
    knowledge_root = (vault / "knowledge").resolve()

    async def gate(tool_name, tool_input, _context):
        print(f"    [callback] tool={tool_name} input_keys={list(tool_input.keys())}", flush=True)
        if tool_name not in ("Write", "Edit"):
            print(f"    [callback]   → ALLOW (not Write/Edit)", flush=True)
            return PermissionResultAllow()
        raw_path = tool_input.get("file_path", "")
        try:
            resolved = Path(raw_path).resolve()
        except (OSError, ValueError) as e:
            print(f"    [callback]   → DENY (unresolvable: {e})", flush=True)
            return PermissionResultDeny(message=f"unresolvable path: {e}")
        try:
            resolved.relative_to(knowledge_root)
        except ValueError:
            msg = f"path-scope: {tool_name} restricted to knowledge/; got {resolved}"
            print(f"    [callback]   → DENY ({msg})", flush=True)
            return PermissionResultDeny(message=msg)
        print(f"    [callback]   → ALLOW (under knowledge/)", flush=True)
        return PermissionResultAllow()

    return gate


@dataclass
class ProbeOutcome:
    label: str
    target_path: Path
    expected_on_disk: bool
    actual_on_disk: bool
    write_tool_uses: list[dict]          # input dicts of every Write attempt
    tool_results: list[dict]             # {'is_error', 'content', 'name'}
    text_summary: str                    # joined TextBlock content

    @property
    def matches_expectation(self) -> bool:
        return self.expected_on_disk == self.actual_on_disk


async def run_probe(label: str, prompt: str, cwd: Path, target_path: Path,
                    expected_on_disk: bool,
                    allowed_tools: list[str] | None = None,
                    can_use_tool=None) -> ProbeOutcome:
    """Run one SDK call against a given allowed_tools / can_use_tool combo."""
    print(f"\n=== {label} ===", flush=True)
    print(f"  prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}", flush=True)
    print(f"  cwd:    {cwd}", flush=True)
    print(f"  target: {target_path}", flush=True)
    print(f"  expect on disk after: {expected_on_disk}", flush=True)
    print(f"  allowed_tools: {allowed_tools or PRODUCTION_ALLOWED_TOOLS}", flush=True)
    print(f"  can_use_tool:  {'yes' if can_use_tool else 'no'}", flush=True)

    write_tool_uses: list[dict] = []
    tool_results: list[dict] = []
    text_chunks: list[str] = []

    # When the callback is the gate, drop acceptEdits — that's what would
    # otherwise auto-allow Write/Edit and bypass the callback.
    perm_mode = "default" if can_use_tool is not None else "acceptEdits"
    options_kwargs = dict(
        cwd=str(cwd),
        model="claude-haiku-4-5",  # cheap; verify pattern not model
        allowed_tools=allowed_tools or PRODUCTION_ALLOWED_TOOLS,
        permission_mode=perm_mode,
        max_turns=3,
        setting_sources=["project"],
        system_prompt="You are a probe agent. Follow the user's instruction precisely. "
                      "If a tool call is denied, report that fact in your text response.",
    )
    if can_use_tool is not None:
        options_kwargs["can_use_tool"] = can_use_tool
    options = ClaudeAgentOptions(**options_kwargs)

    # can_use_tool requires streaming mode (AsyncIterable prompt).
    async def _stream_prompt():
        yield {"type": "user", "message": {"role": "user", "content": prompt}}

    query_prompt = _stream_prompt() if can_use_tool is not None else prompt

    async for message in query(prompt=query_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                name = type(block).__name__
                if name == "TextBlock":
                    text_chunks.append(getattr(block, "text", ""))
                elif name == "ToolUseBlock":
                    tool_name = getattr(block, "name", "")
                    tool_input = getattr(block, "input", {})
                    if tool_name in ("Write", "Edit"):
                        write_tool_uses.append({"tool": tool_name, "input": tool_input})
                    print(f"  → tool_use {tool_name}: {json.dumps(tool_input)[:120]}", flush=True)
        elif isinstance(message, UserMessage):
            if isinstance(message.content, list):
                for block in message.content:
                    if type(block).__name__ == "ToolResultBlock":
                        tool_results.append({
                            "is_error": getattr(block, "is_error", None),
                            "content": str(getattr(block, "content", ""))[:200],
                        })
                        err_flag = "ERR" if getattr(block, "is_error", False) else "ok "
                        print(f"  ← tool_result [{err_flag}]: "
                              f"{str(getattr(block, 'content', ''))[:120]}", flush=True)
        elif isinstance(message, ResultMessage):
            cost = getattr(message, "total_cost_usd", None) or 0
            print(f"  result: stop_reason=? cost=${cost:.4f}", flush=True)

    actual = target_path.exists()
    print(f"  on disk after: {actual} (expected {expected_on_disk})", flush=True)
    return ProbeOutcome(
        label=label,
        target_path=target_path,
        expected_on_disk=expected_on_disk,
        actual_on_disk=actual,
        write_tool_uses=write_tool_uses,
        tool_results=tool_results,
        text_summary=" ".join(text_chunks).strip(),
    )


async def main_async() -> int:
    with tempfile.TemporaryDirectory(prefix="compile-scope-probe-") as tmpdir:
        vault = Path(tmpdir)
        (vault / "knowledge").mkdir()

        inside_target = vault / "knowledge" / "inside.md"
        outside_target = vault / "outside.md"

        # Use absolute paths in the prompts so the model can't normalise
        # `knowledge/foo.md` into `/knowledge/foo.md` (filesystem root).
        # Production uses Opus with cwd=vault and the model resolves the
        # relative path it sees in the prompt against cwd; the SDK passes
        # whatever the model emits straight through to `--allowedTools`
        # matching. Telling the model the exact absolute path strips
        # model-quirks out of the experiment.
        inside = await run_probe(
            label="INSIDE-SCOPE (positive control, absolute path under cwd/knowledge/)",
            prompt=(
                f"Use the Write tool to write the literal markdown text "
                f"`inside-ok` to the absolute path `{inside_target}`. "
                "Pass that exact string as the `file_path` argument. "
                "Do nothing else."
            ),
            cwd=vault,
            target_path=inside_target,
            expected_on_disk=True,
        )

        outside = await run_probe(
            label="OUTSIDE-SCOPE (production allowlist, expecting deny)",
            prompt=(
                f"Use the Write tool to write the literal markdown text "
                f"`outside-bad` to the absolute path `{outside_target}`. "
                "Pass that exact string as the `file_path` argument. "
                "Do nothing else."
            ),
            cwd=vault,
            target_path=outside_target,
            expected_on_disk=False,
        )

        # Clean up the outside.md file the second probe may have created
        # so the can_use_tool probe starts fresh and we can attribute the
        # final on-disk state to the gate alone.
        if outside_target.exists():
            outside_target.unlink()

        outside_via_callback = await run_probe(
            label="OUTSIDE-SCOPE-CALLBACK (can_use_tool gate, expecting deny)",
            prompt=(
                f"Use the Write tool to write the literal markdown text "
                f"`outside-bad-callback` to the absolute path `{outside_target}`. "
                "Pass that exact string as the `file_path` argument. "
                "Do nothing else."
            ),
            cwd=vault,
            target_path=outside_target,
            expected_on_disk=False,
            allowed_tools=CALLBACK_ALLOWED_TOOLS,
            can_use_tool=make_knowledge_only_gate(vault),
        )

        # ── Verdict ────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("VERDICT")
        print("=" * 60)
        outcomes = (inside, outside, outside_via_callback)
        for o in outcomes:
            status = "PASS" if o.matches_expectation else "FAIL"
            print(f"  [{status}] {o.label}")
            print(f"          expected_on_disk={o.expected_on_disk}  "
                  f"actual_on_disk={o.actual_on_disk}")
            print(f"          write_tool_uses={len(o.write_tool_uses)}  "
                  f"tool_results={len(o.tool_results)}")
            if o.tool_results:
                for r in o.tool_results:
                    print(f"            result is_error={r['is_error']!r}: "
                          f"{r['content'][:80]}")
            if o.text_summary:
                print(f"          said: {o.text_summary[:120]}")

        all_pass = all(o.matches_expectation for o in outcomes)
        print()
        print(f"  production allowlist (Write(knowledge/**)):  "
              f"inside={'✓' if inside.matches_expectation else '✗'}  "
              f"outside={'✓' if outside.matches_expectation else '✗'}")
        print(f"  can_use_tool callback:                       "
              f"outside={'✓' if outside_via_callback.matches_expectation else '✗'}")
        print()
        if all_pass:
            print("✓ All three probes match expectation.")
            return 0
        if not outside.matches_expectation and outside_via_callback.matches_expectation:
            print("✗ Production allowlist is DECORATIVE — `Write(knowledge/**)` is")
            print("  not honored as a path-scope by the bundled CLI. The callback")
            print("  path WORKS — switch compile.py + dream.py to can_use_tool.")
        return 1


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n(probe aborted)", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
