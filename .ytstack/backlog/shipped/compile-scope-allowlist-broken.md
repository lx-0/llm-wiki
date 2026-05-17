# Compile-scope allowlist is broken — empirically verified

**Status:** IMPLEMENTED — gate live behind `features.compile_callback_gate=true` (default). Production-verify pending on lxw vault.
**Commits:** `fd3a814` (finding + probe), `478a127` (gate helpers + config + migration + tests), `d8a0de5` (compile.py + dream.py wiring)
**Date:** 2026-05-17
**Severity:** real but bounded — only the path-scope LAYER 2 defense was broken; LAYER 1 (prompt SCOPE block) still holds

## TL;DR

Commit `57fc0d4` ("fix(compile): scope agent write/edit to knowledge/** only — UNTESTED") added `"Write(knowledge/**)"` + `"Edit(knowledge/**)"` to `allowed_tools` in `scripts/compile.py` (and `scripts/dream.py` since). The commit message honestly flagged the assumption as untested.

**The assumption is wrong.** Empirical probe (`scripts/probe_compile_scope.py`, 3 cases against bundled Claude Code CLI 2.1.97 + Haiku) shows the bundled CLI parses `Write(knowledge/**)` as the bare `Write` tool and ignores the parenthesised path glob. The CLI help confirms only `Bash(<shell-pattern>)` syntax is officially supported — the analogous extension to `Write(<path-glob>)` was wishful.

Production effect: the compile agent (and dream agent) currently has unrestricted Write/Edit access to the entire `<vault>/` filesystem under cwd. The only thing keeping it from doing damage is LAYER 1 — the SCOPE block in `prompts/compile_main_system.md` telling the model to only write under `knowledge/`. Prompt injection via substrate, if it bypasses LAYER 1, would not be caught by LAYER 2.

## Probe results

Reproducer: `uv run --quiet python scripts/probe_compile_scope.py` (cost ~$0.03 with Haiku, three SDK calls against a throwaway tmp vault).

```
  production allowlist (Write(knowledge/**)):  inside=✓  outside=✗
  can_use_tool callback:                       outside=✓
```

- **Probe 1 / INSIDE-SCOPE**: Write to `<cwd>/knowledge/inside.md` with production allowlist → file appears. (Positive control passes.)
- **Probe 2 / OUTSIDE-SCOPE**: Write to `<cwd>/outside.md` (NOT under knowledge/) with production allowlist → **file appears**. (Should have been denied.)
- **Probe 3 / OUTSIDE-SCOPE-CALLBACK**: Same write, but with `allowed_tools=["Read","Glob","Grep"]` (no Write/Edit) plus a `can_use_tool` callback that rejects paths outside `<cwd>/knowledge/` → file does NOT appear. (Deny enforced.)

The callback path is bulletproof — it's a Python-side gate, not subject to CLI parsing semantics.

## Why production hasn't blown up

LAYER 1 (the SCOPE block in `compile_main_system.md`) instructs the model to only Write under `knowledge/`. The model obeys most of the time. The original 2026-05-15 incident was prompt injection via substrate content describing engine changes — that was a corner case where the model interpreted source-as-instruction. With LAYER 1 alone, similar injection attempts that the model resists naturally don't surface as bugs.

LAYER 2 (the supposed path-scope) was meant to be belt-and-suspenders. The belt was always missing; only the suspenders held.

## Proposed fix — switch to `can_use_tool` callback

Replace the decorative path-scope with a real Python-side gate. Concrete shape (would apply to both `compile.py` and `dream.py`, plus any other site using `Write(knowledge/**)`):

```python
from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    query,
)

def make_knowledge_only_gate(vault: Path):
    knowledge_root = (vault / "knowledge").resolve()
    async def gate(tool_name, tool_input, _context):
        if tool_name not in ("Write", "Edit"):
            return PermissionResultAllow()
        try:
            resolved = Path(tool_input.get("file_path", "")).resolve()
            resolved.relative_to(knowledge_root)
        except ValueError:
            return PermissionResultDeny(
                message=f"path-scope: {tool_name} restricted to knowledge/; got {resolved}"
            )
        return PermissionResultAllow()
    return gate

# in query() call:
options = ClaudeAgentOptions(
    cwd=str(ROOT_DIR),
    model=model_id,
    allowed_tools=["Read", "Glob", "Grep"],          # NO Write/Edit here
    can_use_tool=make_knowledge_only_gate(ROOT_DIR), # the actual gate
    permission_mode="default",                       # NOT acceptEdits
    setting_sources=["project"],
    ...
)

# Prompt must be an AsyncIterable in streaming mode (callback requirement):
async def _stream_prompt():
    yield {"type": "user", "message": {"role": "user", "content": prompt}}

async for message in query(prompt=_stream_prompt(), options=options):
    ...
```

Three constraints to internalise:

1. **Write/Edit must NOT be in `allowed_tools`.** If they are, the CLI fast-paths them as "pre-approved" and never consults the callback (verified in probe 2 retry).
2. **`permission_mode` must NOT be `acceptEdits`.** That mode auto-allows Write/Edit and bypasses the callback. Use `default`.
3. **Prompt must be `AsyncIterable[dict]`, not `str`.** The SDK raises `ValueError: can_use_tool callback requires streaming mode` for string prompts.

Call sites that need the rewrite: `scripts/compile.py` (1 site), `scripts/dream.py` (1 site). Possibly other agent-task callers — needs a grep.

## Alternative considered: denylist

The pre-`57fc0d4` posture used `disallowed_tools` with explicit engine-subtree paths (`.wiki/`, `.ytstack/`, `docs/`, etc.). Reasons not to revert:
- Allowlist is fail-closed; denylist is fail-open. New engine subtree = silent hole.
- The maintenance burden was the reason `57fc0d4` switched away.

Callback is allowlist-in-spirit (only `knowledge/` is allowed) but enforced at the right layer.

## Open questions

1. **Does the streaming-mode rewrite affect anything else compile.py + dream.py rely on?** The prompt-as-string path is well-trodden; AsyncIterable is the streaming path. Worth a careful read of message-loop handling to confirm parity.
2. **Does the callback fire reliably under high token-per-turn load?** Probe used Haiku with simple prompts. Production Opus with 500KB prompts might surface latency or batching edge cases. Plan: ship behind a config flag (`features.compile_use_callback_gate`, default true) so the operator can fall back to current behaviour if pathological.
3. **Should the probe script become a CI smoke test?** Cost is ~$0.03/run with Haiku, network-bound. Maybe weekly piggyback rather than per-commit.

## Honest scope-of-incident

This is a security-posture finding, not a working-system-broken finding. Nothing in the operator's vault has been damaged by the broken path-scope (LAYER 1 has held). But the commit message of `57fc0d4` overstates the protection — REGEL #1 violation surfaced and now verified.

Related backlog: `compile-agent-no-filesystem-write.md` — the long-term refactor that removes the injection surface entirely by having the agent return structured payload via `ResultMessage` and having `compile.py` write files deterministically. That makes the callback-gate moot, but is a much bigger rewrite. The callback fix is the right wedge.
