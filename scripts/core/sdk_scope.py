"""The Write/Edit path-scope gate for Claude-SDK agents.

`run_sdk_query` (`core/sdk_helpers.py`) wires it for every write-scoped call
(`SdkCallSpec.write_scope` → the PreToolUse hook; `deny_all_writes` → the
`can_use_tool` gate); the curiosity folder scan and the reports scope-lock probe
build it directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterable
from pathlib import Path

# ── Path-scope permission gate ──────────────────────────────────────────
#
# The bundled Claude Code CLI does NOT honor `Write(<glob>)` / `Edit(<glob>)`
# patterns in `--allowedTools` as path scopes (only `Bash(<shell-pattern>)`
# is documented). Empirically — `scripts/probe_compile_scope.py`, 2026-05-17
# — those entries are parsed as the bare `Write` / `Edit` tool and the
# parenthesised content is ignored, leaving the agent with unrestricted
# write access under cwd. The fix is a `can_use_tool` callback as the
# actual Python-side gate.
#
# Three constraints when using this callback in a call site:
#   1. Write/Edit must NOT appear in `allowed_tools` — else the CLI
#      fast-paths them as pre-approved and never asks the callback.
#   2. `permission_mode` must NOT be `acceptEdits` — that auto-allows
#      the very tools we're trying to gate.
#   3. `prompt` must be an AsyncIterable[dict] (streaming mode); the SDK
#      raises ValueError for string prompts when a callback is wired.
# `prompt_stream()` below wraps a string into the right shape.


async def prompt_stream(text: str) -> AsyncIterable[dict]:
    """Wrap a plain prompt string in the SDK's streaming-mode envelope.

    The `can_use_tool` callback requires `prompt` to be an AsyncIterable
    of message dicts in `{"type": "user", "message": {"role": "user",
    "content": ...}}` shape. This helper turns a single string into a
    one-message async iterable so call sites don't need to reshape their
    prompt-building logic.
    """
    yield {"type": "user", "message": {"role": "user", "content": text}}


def make_path_scope_gate(allowed_write_roots):
    """Build a `can_use_tool` callback that restricts Write/Edit to the
    given filesystem roots. All other tools (Read/Glob/Grep/Bash/...) are
    allowed unconditionally — gating them is the caller's job via
    `allowed_tools` / `disallowed_tools`.

    Args:
        allowed_write_roots: iterable of `pathlib.Path`. A Write/Edit is
            allowed iff its `file_path` resolves (after `Path.resolve()`)
            inside one of these roots. Symlinks are followed at resolve
            time, so a vault symlink into knowledge/ is honored; an
            outside-the-tree target presented as a relative path under
            cwd is rejected after resolution.

    Returns:
        An async callback compatible with
        `claude_agent_sdk.ClaudeAgentOptions(can_use_tool=...)`.
    """
    # Resolve once at construction time so per-call work stays cheap.
    resolved_roots = [Path(r).resolve() for r in allowed_write_roots]

    # Late import — this module stays import-light when callers don't use the
    # gate, and we don't pay the SDK import cost at module-load time.
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    async def gate(tool_name, tool_input, _context):
        if tool_name not in ("Write", "Edit"):
            return PermissionResultAllow()
        raw_path = tool_input.get("file_path", "")
        if not raw_path:
            return PermissionResultDeny(
                message=f"{tool_name} call missing file_path",
            )
        try:
            resolved = Path(raw_path).resolve()
        except (OSError, ValueError) as exc:
            return PermissionResultDeny(
                message=f"{tool_name} path could not be resolved: {exc}",
            )
        for root in resolved_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return PermissionResultAllow()
        return PermissionResultDeny(
            message=(
                f"{tool_name} path-scope: {resolved} is not under any of "
                f"the permitted roots ({', '.join(str(r) for r in resolved_roots)})."
            ),
        )

    return gate


def make_path_scope_hook(allowed_write_roots, denied_subpaths=None):
    """Build a PreToolUse hook callback that path-scopes Write/Edit.

    Used as the working alternative to ``can_use_tool``: while
    ``make_path_scope_gate`` correctly denies OUTSIDE-scope Write/Edit,
    the bundled CLI exposes neither Write nor Edit to the agent when they
    are absent from ``allowed_tools`` — INSIDE-scope writes were silently
    blocked too (verified empirically against compile + dream on
    2026-05-18, ~16 hours of silent write-failure before discovery).

    The hook architecture works because Write/Edit STAY in
    ``allowed_tools`` (so the CLI exposes them to the agent) but a
    PreToolUse hook fires BEFORE each invocation. The hook returns
    ``permissionDecision: "deny"`` for paths outside ``allowed_write_roots``.

    Args:
        allowed_write_roots: iterable of ``pathlib.Path``. A Write/Edit is
            allowed iff its ``file_path`` resolves (after ``Path.resolve()``)
            inside one of these roots.
        denied_subpaths: optional iterable of ``pathlib.Path``. A write is
            denied if it resolves inside one of these, EVEN when it is also
            inside an allowed root — deny takes precedence over allow. Carves
            a write-protected island out of an allowed root (e.g.
            ``knowledge/facts/`` inside ``knowledge/`` for `correct apply`,
            M028). Defaults to none → existing callers are unchanged.

    Returns:
        An async callback compatible with the
        ``hooks={"PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[...])]}``
        wiring on ``ClaudeAgentOptions``.
    """
    resolved_roots = [Path(r).resolve() for r in allowed_write_roots]
    resolved_denied = [Path(d).resolve() for d in (denied_subpaths or [])]

    async def hook(hook_input, _tool_use_id, _context):
        tool_input = hook_input.get("tool_input") or {}
        raw_path = tool_input.get("file_path", "")
        if not raw_path:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{hook_input.get('tool_name', '?')} missing file_path"
                    ),
                }
            }
        try:
            resolved = Path(raw_path).resolve()
        except (OSError, ValueError) as exc:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (f"path could not be resolved: {exc}"),
                }
            }
        # Deny precedence: a write-protected subpath blocks even allowed roots.
        for denied in resolved_denied:
            try:
                resolved.relative_to(denied)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"{resolved} is under write-protected {denied}"
                        ),
                    }
                }
            except ValueError:
                continue
        for root in resolved_roots:
            try:
                resolved.relative_to(root)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }
            except ValueError:
                continue
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{resolved} not under any permitted root "
                    f"({', '.join(str(r) for r in resolved_roots)})"
                ),
            }
        }

    return hook
