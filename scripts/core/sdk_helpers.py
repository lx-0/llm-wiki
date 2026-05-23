"""Diagnostic helpers for `claude_agent_sdk` calls.

The SDK silently drops the bundled-CLI's stderr unless an
`options.stderr` callback is wired, so failures surface as the
unhelpful `Command failed with exit code 1 - Check stderr output for
details`. Without root-cause info the operator can only guess at
rate-limits, auth failures, network blips, or hard CLI crashes.

This module gives every SDK call site four primitives:

  - ``StderrCapture`` — ring-buffer collector that doubles as the
    ``stderr=`` callback. Holds the last N lines for diagnostic dumps.
  - ``classify_failure`` — heuristic ``FailureClass`` from elapsed
    duration + captured stderr + exception text.
  - ``log_sdk_failure`` — single call site that writes a diagnostic
    record (source, model, input size, elapsed, classification, last
    captured stderr lines) to the caller's logger.
  - ``assert_prompt_within_budget`` — pre-flight guard that rejects a
    corpus-sized prompt *before* the SDK call, where context-window
    overflow would otherwise surface as an opaque ``kind=unknown``.

Use from each SDK call site::

    capture = StderrCapture()
    started = time.time()
    try:
        async for msg in query(prompt=p, options=ClaudeAgentOptions(
            ..., stderr=capture.callback,
        )):
            ...
    except Exception as exc:
        failure = log_sdk_failure(
            log, label="compile_file",
            source=rel_path, model=CONFIG.models.compile_model,
            input_chars=len(src), started=started,
            capture=capture, exc=exc,
        )
        # caller decides retry / continue / abort based on `failure.kind`
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

# Patterns matched against captured stderr + exception text. Order is
# priority — most-specific first.
_RE_RATE_LIMIT = re.compile(
    r"\b(429|rate.?limit(ed)?|overload(ed)?|usage.?limit(ed)?|quota.?exceeded)\b",
    re.IGNORECASE,
)
_RE_AUTH = re.compile(
    r"\b(401|403|unauthori[sz]ed|invalid.?api.?key|authentication.?failed|"
    r"missing.?credentials|expired.?credentials|not.?authenticated)\b",
    re.IGNORECASE,
)
_RE_MODEL = re.compile(
    r"(invalid.?model|model.?not.?found|unknown.?model|model.?does.?not.?exist|"
    r"no.?such.?model)",
    re.IGNORECASE,
)
_RE_NETWORK = re.compile(
    r"(ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|connection.?reset|"
    r"connection.?refused|getaddrinfo|fetch.?failed|socket.?hang.?up|"
    r"network.?error)",
    re.IGNORECASE,
)
_RE_OOM = re.compile(
    r"(out.?of.?memory|heap.?out|JavaScript.?heap|FATAL.*memory|allocation.?failed)",
    re.IGNORECASE,
)


@dataclass
class StderrCapture:
    """Ring-buffer collector for bundled-CLI stderr lines.

    Pass ``.callback`` to ``ClaudeAgentOptions(stderr=...)``. After the
    call, ``.lines`` holds the most-recent N entries (default 200).
    """

    max_lines: int = 200
    lines: deque = field(init=False)

    def __post_init__(self) -> None:
        self.lines = deque(maxlen=self.max_lines)

    def callback(self, line: str) -> None:
        line = line.rstrip("\n").rstrip()
        if line:
            self.lines.append(line)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def dump_to(self, log: logging.Logger, indent: str = "    ") -> None:
        """Write captured lines to ``log`` at WARNING level so they also
        land in any `*-errors.log` handler. Empty buffer prints a single
        marker line so silent CLI crashes are distinguishable from a
        missing instrumentation site."""
        if not self.lines:
            log.warning(
                "%s[CLI-STDERR] (empty — bundled CLI exited without writing to stderr)",
                indent,
            )
            return
        log.warning("%s[CLI-STDERR] %d line(s) captured:", indent, len(self.lines))
        for line in self.lines:
            log.warning("%s  %s", indent, line)


@dataclass(frozen=True)
class FailureClass:
    """Classification of one failed SDK call."""

    kind: str   # rate_limit | auth | model | network | oom | cli_crash | max_turns | tokens_exceeded | unknown
    detail: str

    def __str__(self) -> str:  # pragma: no cover — formatting only
        return f"{self.kind}: {self.detail}"


class PromptTooLargeError(Exception):
    """Raised by ``assert_prompt_within_budget`` when an assembled LLM
    prompt exceeds the configured character budget — a pre-flight catch
    for context-window overflow that would otherwise surface as an opaque
    exit-1 / empty-stderr ``kind=unknown`` SDK failure."""


def assert_prompt_within_budget(
    prompt_chars: int,
    limit_chars: int,
    *,
    label: str,
    breakdown: dict[str, int] | None = None,
) -> None:
    """Raise ``PromptTooLargeError`` if ``prompt_chars`` exceeds ``limit_chars``.

    Catches a corpus-sized prompt *before* the SDK call. Without this the
    bundled CLI dies silently mid-request and ``classify_failure`` can only
    report ``kind=unknown`` — empty stderr, variable timing, no signal to
    match on. ``breakdown`` is an optional ``{component: chars}`` map so the
    operator sees which embedded part bloated.
    """
    if prompt_chars <= limit_chars:
        return
    detail = ""
    if breakdown:
        detail = " — " + ", ".join(
            f"{name} {n:,} chars" for name, n in breakdown.items()
        )
    raise PromptTooLargeError(
        f"{label}: assembled prompt is {prompt_chars:,} chars, over the "
        f"{limit_chars:,}-char budget{detail}. The input has outgrown an "
        f"inline LLM call — prune the embedded content, or raise the limit "
        f"in config.yaml if the model's context window allows."
    )


def classify_failure(
    elapsed_s: float,
    captured_text: str,
    exc_text: str = "",
) -> FailureClass:
    """Best-effort classification combining stderr + exception + duration.

    Heuristics in priority order:
      1. explicit keyword match in stderr/exc text — most reliable
      2. very short elapsed (< 5s) → bundled CLI crashed fast
      3. fallback "unknown" — operator should read captured lines
    """
    haystack = f"{captured_text}\n{exc_text}"
    if _RE_RATE_LIMIT.search(haystack):
        return FailureClass("rate_limit", "matched 429/overload/quota pattern")
    if _RE_AUTH.search(haystack):
        return FailureClass("auth", "matched auth/credentials pattern")
    if _RE_MODEL.search(haystack):
        return FailureClass("model", "matched invalid-model pattern")
    if _RE_NETWORK.search(haystack):
        return FailureClass("network", "matched network-error pattern")
    if _RE_OOM.search(haystack):
        return FailureClass("oom", "stderr suggested out-of-memory")
    if elapsed_s < 5.0:
        if not captured_text.strip():
            return FailureClass(
                "cli_crash",
                f"failed in {elapsed_s:.1f}s with empty stderr — bundled CLI exited silently",
            )
        return FailureClass(
            "cli_crash",
            f"failed in {elapsed_s:.1f}s — bundled CLI exited fast (see stderr)",
        )
    return FailureClass(
        "unknown",
        f"failed after {elapsed_s:.1f}s — see captured stderr/exception",
    )


def log_sdk_failure(
    log: logging.Logger,
    *,
    label: str,
    started: float,
    capture: StderrCapture,
    exc: BaseException,
    source: str | None = None,
    model: str | None = None,
    input_chars: int | None = None,
    extra: dict | None = None,
) -> FailureClass:
    """Single call point for SDK failure diagnostics. Returns the FailureClass.

    Writes ERROR-level records so they land in the caller's
    `*-errors.log` (compile.py + flush.py both wire one). Each call
    emits: classification, source path, model, input size, elapsed,
    exception text, then the captured CLI stderr lines.
    """
    elapsed = time.time() - started
    exc_text = f"{type(exc).__name__}: {exc}"
    cls = classify_failure(elapsed, capture.text, exc_text)

    log.error(
        "  %s ✗ failed after %.1fs — kind=%s · %s",
        label, elapsed, cls.kind, cls.detail,
    )
    if source is not None:
        log.error("    source:    %s", source)
    if model is not None:
        log.error("    model:     %s", model)
    if input_chars is not None:
        log.error(
            "    input:     %s chars (%.1f KB)",
            f"{input_chars:,}", input_chars / 1024,
        )
    if extra:
        for k, v in extra.items():
            log.error("    %s: %s", k, v)
    log.error("    exception: %s", exc_text)
    capture.dump_to(log)
    return cls


def is_fatal(failure: FailureClass) -> bool:
    """True if continuing the run is pointless until operator fixes config.

    Auth + invalid-model errors will fail identically on the next call.
    Cost-exceeded means the per-file budget guard fired — continuing the
    batch would likely burn the same money on the next file (same prompt /
    same substrate / same loop pattern). Operator must intervene
    (increase the budget knob, or skip the offending substrate type).
    Rate-limit + network + cli_crash + max_turns + unknown are potentially
    transient and don't fail-fast.
    """
    return failure.kind in {"auth", "model", "tokens_exceeded"}


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

from collections.abc import AsyncIterable  # noqa: E402  (after other imports)
from pathlib import Path  # noqa: E402


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

    # Late import — sdk_helpers stays import-light when callers don't use the
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


def make_path_scope_hook(allowed_write_roots):
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

    Returns:
        An async callback compatible with the
        ``hooks={"PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[...])]}``
        wiring on ``ClaudeAgentOptions``.
    """
    resolved_roots = [Path(r).resolve() for r in allowed_write_roots]

    async def hook(hook_input, _tool_use_id, _context):
        tool_input = hook_input.get("tool_input") or {}
        raw_path = tool_input.get("file_path", "")
        if not raw_path:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{hook_input.get('tool_name', '?')} missing file_path"
                ),
            }}
        try:
            resolved = Path(raw_path).resolve()
        except (OSError, ValueError) as exc:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"path could not be resolved: {exc}"
                ),
            }}
        for root in resolved_roots:
            try:
                resolved.relative_to(root)
                return {"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }}
            except ValueError:
                continue
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{resolved} not under any permitted root "
                f"({', '.join(str(r) for r in resolved_roots)})"
            ),
        }}
    return hook
