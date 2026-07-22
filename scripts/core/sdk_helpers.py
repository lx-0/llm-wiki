"""Claude-SDK call harness + diagnostic helpers for `claude_agent_sdk`.

The SDK silently drops the bundled-CLI's stderr unless an
`options.stderr` callback is wired, so failures surface as the
unhelpful `Command failed with exit code 1 - Check stderr output for
details`. Without root-cause info the operator can only guess at
rate-limits, auth failures, network blips, or hard CLI crashes.

The primary interface is the ``run_sdk_query(prompt, spec)`` harness
(M021 slice 1): one deep seam that owns the *mechanics* every call site
used to hand-roll — ``ClaudeAgentOptions`` assembly, path-scope gate
wiring, the per-message stall-timeout loop, stderr capture, failure
classification/logging, cache-aware usage extraction, and LEDGER
recording. *Policy* stays caller-owned via ``SdkCallSpec``: which model,
which tools, which write scope, which timeout — every site differs, and
hiding those knobs was explicitly rejected in DECISIONS 2026-05-04.

Use from a call site::

    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label="compile_file", logger=log, model=model_id,
            cwd=ROOT_DIR, max_turns=12, system_prompt=...,
            allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
            write_scope=WriteScope(roots=(knowledge_dir,)),
            stall_timeout_s=600, source=rel_path,
        ),
        query_fn=query,  # module-global so tests can monkeypatch it
    )
    if result.failure is not None:
        ...  # caller decides retry / skip / abort from `failure.kind`

Lower-level primitives (used by the harness, still available for
non-``query()`` diagnostics):

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
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

from .errors import swallow

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


@dataclass(frozen=True)
class UsageTokens:
    """Token counts extracted from one SDK message's ``usage`` dict.

    The bundled CLI enables prompt caching by default, so for any non-trivial
    prompt the bulk of the *real* input lands in ``cache_creation_input_tokens``
    (first turn that writes the cache) + ``cache_read_input_tokens`` (every
    subsequent turn that re-reads it) — NOT in ``input_tokens``, which holds
    only the small uncached delta. Summing ``input_tokens`` alone undercounts
    true input by orders of magnitude and makes a healthy cached call look like
    a no-op (``in:12`` for a 40 KB prompt while the API bills $0.79 of cache
    tokens). Use ``total_input`` for any "did the substrate actually get
    processed?" heuristic and for ledger accounting.
    """

    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_input(self) -> int:
        """Uncached input + cache-creation + cache-read — the true input size."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


def extract_usage_tokens(usage: dict | None) -> UsageTokens:
    """Pull input/cache/output token counts from an SDK message ``usage`` dict.

    Tolerant of ``None`` / missing keys / non-int values (returns zeros). The
    ``usage`` payload is a raw API passthrough (``dict[str, Any]``), so the
    cache keys are present only when prompt caching was active for that turn.
    Prefer the ``ResultMessage.usage`` (authoritative cumulative session total)
    over summing per-turn ``AssistantMessage.usage`` — the latter double-counts
    ``cache_read_input_tokens`` across turns.
    """
    if not usage:
        return UsageTokens()

    def _g(key: str) -> int:
        try:
            return int(usage.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return UsageTokens(
        input_tokens=_g("input_tokens"),
        cache_creation_tokens=_g("cache_creation_input_tokens"),
        cache_read_tokens=_g("cache_read_input_tokens"),
        output_tokens=_g("output_tokens"),
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
        # Deny precedence: a write-protected subpath blocks even allowed roots.
        for denied in resolved_denied:
            try:
                resolved.relative_to(denied)
                return {"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{resolved} is under write-protected {denied}"
                    ),
                }}
            except ValueError:
                continue
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


# ── run_sdk_query — the one Claude-SDK call harness (M021 slice 1) ─────
#
# Every hand-rolled `async for message in query(...)` loop in the engine
# re-implemented the same mechanics with drift: stderr capture, per-message
# stall timeout, isinstance dispatch, usage summing (six sites summed the
# documented-wrong uncached `usage["input_tokens"]` delta — see UsageTokens),
# LEDGER recording, failure classification. The harness owns those mechanics
# once. Policy stays caller-owned via SdkCallSpec (DECISIONS 2026-05-04:
# every site has different tools/turns/permissions/system-prompt — do not
# hide ClaudeAgentOptions knobs, parameterize them).
#
# Token accounting follows DECISIONS 2026-06-02 (dual basis):
#   - `input_tokens`/`output_tokens` on the result are CACHE-INCLUSIVE
#     (ResultMessage.usage preferred, per-turn cache-inclusive sum as
#     fallback) — this is what the harness records to LEDGER.
#   - `uncached_input_tokens`/`uncached_output_tokens` are the raw per-turn
#     sums — the stable basis for runaway-budget guards (cache_read is
#     re-counted per turn and would explode a tuned threshold).


@dataclass(frozen=True)
class WriteScope:
    """Path-scope for agent Write/Edit, wired by the harness.

    Production shape (2026-05-18): Write/Edit stay in ``allowed_tools`` so
    the CLI exposes them, and a PreToolUse hook (``make_path_scope_hook``)
    denies any write outside ``roots`` (with ``denied_subpaths`` carving
    write-protected islands, deny-precedence).

    ``legacy_allowed_tools`` is the pre-hook rollback shape
    (``Write(<glob>)`` pseudo-scopes + ``acceptEdits``), used only when set
    AND ``CONFIG.features.compile_callback_gate`` is off — keeps the
    rollback one config flip away, exactly as the per-site branches did.
    """

    roots: tuple[Path, ...]
    denied_subpaths: tuple[Path, ...] = ()
    legacy_allowed_tools: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SdkCallSpec:
    """Per-site policy for one ``run_sdk_query`` call.

    The harness unifies mechanics, not policy: tool sets, turn budgets,
    permission modes, system prompts, timeouts and write scopes differ at
    every site and stay here, caller-owned. ``None`` means "omit — let the
    SDK/CLI default apply" (e.g. ``model=None`` runs the CLI's default
    model; ``stall_timeout_s=None`` disables the per-message timeout).

    The 3-layer substrate-injection scope enforcement (prompt + tools +
    setting_sources) is preserved: the caller controls ``allowed_tools`` /
    ``disallowed_tools`` / ``setting_sources`` explicitly, and write access
    is gated via ``write_scope`` / ``deny_all_writes``.
    """

    label: str                                     # diagnostic label for logs
    logger: logging.Logger                         # caller's logger (errors land in its *-errors.log)
    model: str | None = None
    cwd: Path | None = None
    max_turns: int | None = None
    system_prompt: str | dict | None = None
    allowed_tools: tuple[str, ...] | None = None
    disallowed_tools: tuple[str, ...] | None = None
    permission_mode: str | None = None
    setting_sources: tuple[str, ...] | None = None
    write_scope: WriteScope | None = None          # hook-gated Write/Edit path scope
    deny_all_writes: bool = False                  # read-only wedge (M019): can_use_tool deny-all
    stall_timeout_s: float | None = None           # per-MESSAGE stall timeout, not wall-clock
    source: str | None = None                      # provenance string for failure logs
    input_chars: int | None = None                 # defaults to len(prompt)
    extra_log: dict | None = None                  # extra key/values for log_sdk_failure
    record_usage: bool = True                      # LEDGER.record on every outcome


@dataclass(frozen=True)
class SdkRunResult:
    """Typed outcome of one ``run_sdk_query`` call.

    ``failure is None`` means the stream completed without an SDK-level
    error. ``input_tokens``/``output_tokens`` are the cache-inclusive
    totals (the LEDGER basis); ``uncached_*`` are the raw per-turn sums
    (the runaway-budget basis) — see DECISIONS 2026-06-02.
    """

    result_text: str = ""              # ResultMessage.result (final agent text)
    assistant_text: str = ""           # concatenated AssistantMessage TextBlocks
    input_tokens: int = 0              # cache-inclusive true input (LEDGER basis)
    output_tokens: int = 0
    uncached_input_tokens: int = 0     # raw per-turn sum (budget-guard basis)
    uncached_output_tokens: int = 0
    cost_usd: float = 0.0              # SDK-reported actual (ResultMessage.total_cost_usd)
    message_count: int = 0
    num_turns: int = 0
    subtype: str | None = None         # ResultMessage.subtype when one arrived
    failure: FailureClass | None = None
    exc: BaseException | None = None   # original exception for `raise ... from`
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.failure is None


def _structured_error_failure(final_result, elapsed_s: float, uncached_tokens: int) -> FailureClass:
    """FailureClass for a structured ``ResultMessage(is_error=True)``.

    ``error_max_turns`` maps to kind=max_turns; everything else routes
    through the shared classifier so a fast empty-stderr fail lands as
    cli_crash and a slow no-signal fail as unknown (which retry ladders
    treat differently from an opaque agent_error).
    """
    errors = getattr(final_result, "errors", None) or []
    if final_result.subtype == "error_max_turns":
        kind = "max_turns"
    else:
        kind = classify_failure(
            elapsed_s, final_result.result or "", "; ".join(errors),
        ).kind
    detail = (
        f"{final_result.subtype} after {final_result.num_turns} turns "
        f"({elapsed_s:.1f}s, {uncached_tokens:,} tok)"
    )
    if errors:
        detail += f" — errors: {'; '.join(errors)}"
    return FailureClass(kind, detail)


async def run_sdk_query(prompt: str, spec: SdkCallSpec, *, query_fn=None) -> SdkRunResult:
    """Run one Claude-SDK ``query()`` end-to-end. Never raises for SDK
    failures — returns an ``SdkRunResult`` with ``failure`` set instead,
    so callers keep full control of retry/skip/abort policy.

    ``query_fn`` defaults to ``claude_agent_sdk.query``; call sites pass
    their module-global ``query`` so tests keep monkeypatching the site's
    own symbol (``monkeypatch.setattr(<mod>, "query", fake)``).

    Mechanics owned here:
      - options assembly (buffer size from CONFIG, stderr capture wired)
      - write gating: ``spec.write_scope`` → PreToolUse path-scope hook
        (production, 2026-05-18) or the legacy glob shape when the
        ``compile_callback_gate`` flag is off; ``spec.deny_all_writes`` →
        ``can_use_tool`` deny-all gate + streaming prompt (the callback
        contract requires an AsyncIterable prompt)
      - per-message stall-timeout loop (surfaces bundled-CLI hangs as
        kind=timeout instead of blocking forever)
      - cache-aware usage extraction on BOTH bases (see module comment)
      - ``LEDGER.record`` on every outcome — success, structured error,
        timeout, crash — with the cache-inclusive totals
      - failure classification + ERROR-level diagnostics via
        ``log_sdk_failure`` / ``StderrCapture``
    """
    # Late imports: sdk_helpers stays import-light for callers that only
    # use the diagnostics primitives, and tests that monkeypatch
    # `core.usage.LEDGER` / `classify_failure` see the swap at call time.
    import asyncio

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
    )
    from claude_agent_sdk import query as _sdk_query

    from .config import CONFIG
    from .usage import LEDGER, PROVIDER_CLAUDE

    if query_fn is None:
        query_fn = _sdk_query

    log = spec.logger
    capture = StderrCapture()
    started = time.time()
    input_chars = spec.input_chars if spec.input_chars is not None else len(prompt)
    timeout = spec.stall_timeout_s if (spec.stall_timeout_s or 0) > 0 else None

    # ── options assembly ──────────────────────────────────────────────
    options_kwargs: dict = dict(
        max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
        stderr=capture.callback,
    )
    if spec.cwd is not None:
        options_kwargs["cwd"] = str(spec.cwd)
    if spec.model is not None:
        options_kwargs["model"] = spec.model
    if spec.max_turns is not None:
        options_kwargs["max_turns"] = spec.max_turns
    if spec.system_prompt is not None:
        options_kwargs["system_prompt"] = spec.system_prompt
    if spec.setting_sources is not None:
        options_kwargs["setting_sources"] = list(spec.setting_sources)
    if spec.disallowed_tools is not None:
        options_kwargs["disallowed_tools"] = list(spec.disallowed_tools)

    query_prompt: object = prompt
    if spec.deny_all_writes:
        # Read-only wedge composition (M019): deny-all-writes can_use_tool
        # gate as defense-in-depth under permission_mode="default". The
        # callback contract requires a streaming prompt (prompt_stream).
        options_kwargs["allowed_tools"] = list(spec.allowed_tools or ())
        options_kwargs["permission_mode"] = spec.permission_mode or "default"
        options_kwargs["can_use_tool"] = make_path_scope_gate([])
        query_prompt = prompt_stream(prompt)
    elif spec.write_scope is not None:
        scope = spec.write_scope
        if (
            scope.legacy_allowed_tools is not None
            and not CONFIG.features.compile_callback_gate
        ):
            # Rollback shape (pre-2026-05-18): Write(<glob>) pseudo-scopes
            # + acceptEdits. One config flip away, per-site branch removed.
            options_kwargs["allowed_tools"] = list(scope.legacy_allowed_tools)
            options_kwargs["permission_mode"] = "acceptEdits"
        else:
            # Production write gate (2026-05-18): Write/Edit stay exposed
            # in allowed_tools; the PreToolUse hook path-scopes them.
            options_kwargs["allowed_tools"] = list(spec.allowed_tools or ())
            options_kwargs["hooks"] = {
                "PreToolUse": [
                    HookMatcher(
                        matcher="Write|Edit",
                        hooks=[make_path_scope_hook(
                            list(scope.roots),
                            denied_subpaths=list(scope.denied_subpaths) or None,
                        )],
                    ),
                ],
            }
            options_kwargs["permission_mode"] = spec.permission_mode or "default"
    else:
        if spec.allowed_tools is not None:
            options_kwargs["allowed_tools"] = list(spec.allowed_tools)
        if spec.permission_mode is not None:
            options_kwargs["permission_mode"] = spec.permission_mode

    options = ClaudeAgentOptions(**options_kwargs)

    # ── accumulation state ────────────────────────────────────────────
    uncached_in = uncached_out = 0        # raw per-turn sums (budget basis)
    fallback_in = fallback_out = 0        # cache-inclusive per-turn fallback
    text_parts: list[str] = []
    final_result = None
    result_text = ""
    message_count = 0

    def _record(input_tokens: int, output_tokens: int) -> None:
        """LEDGER gets the cache-inclusive totals on EVERY outcome —
        partial usage from a failed call is still real spend."""
        if spec.record_usage:
            LEDGER.record(
                model=spec.model or "(default)",
                provider=PROVIDER_CLAUDE,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

    def _partial_result(failure: FailureClass, exc: BaseException | None) -> SdkRunResult:
        return SdkRunResult(
            result_text=result_text,
            assistant_text="".join(text_parts),
            input_tokens=fallback_in,
            output_tokens=fallback_out,
            uncached_input_tokens=uncached_in,
            uncached_output_tokens=uncached_out,
            cost_usd=0.0,
            message_count=message_count,
            num_turns=final_result.num_turns if final_result is not None else 0,
            subtype=final_result.subtype if final_result is not None else None,
            failure=failure,
            exc=exc,
            elapsed_s=time.time() - started,
        )

    # ── the one message loop ──────────────────────────────────────────
    try:
        agen = query_fn(prompt=query_prompt, options=options).__aiter__()
        while True:
            try:
                if timeout is not None:
                    message = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
                else:
                    message = await agen.__anext__()
            except StopAsyncIteration:
                break
            message_count += 1
            if isinstance(message, AssistantMessage):
                usage = getattr(message, "usage", None)
                if usage:
                    u = extract_usage_tokens(usage)
                    uncached_in += u.input_tokens
                    uncached_out += u.output_tokens
                    fallback_in += u.total_input
                    fallback_out += u.output_tokens
                for block in getattr(message, "content", None) or ():
                    if type(block).__name__ == "TextBlock":
                        text_parts.append(getattr(block, "text", ""))
            elif isinstance(message, ResultMessage):
                final_result = message
                result_text = message.result or ""
    except asyncio.TimeoutError:
        elapsed = time.time() - started
        log.warning(
            "  %s ⏱ per-call timeout after %.1fs (no message for %ss, "
            "messages so far=%d) — bundled CLI hung. model=%s source=%s (%s chars).",
            spec.label, elapsed, timeout, message_count,
            spec.model or "(default)", spec.source or "—", f"{input_chars:,}",
        )
        # Best-effort cleanup — a second failure while closing a hung
        # stream is expected, log it at debug only.
        with swallow("sdk stream aclose after timeout", level="debug", logger=log):
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                await aclose()
        log_sdk_failure(
            log,
            label=spec.label,
            source=spec.source,
            model=spec.model,
            input_chars=input_chars,
            started=started,
            capture=capture,
            exc=TimeoutError(
                f"per-call timeout after {elapsed:.1f}s (stall_timeout_s={timeout})"
            ),
            extra=spec.extra_log,
        )
        _record(fallback_in, fallback_out)
        return _partial_result(
            FailureClass(
                "timeout",
                f"per-call stall after {elapsed:.1f}s (messages={message_count})",
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001 — classified below, caller decides
        elapsed = time.time() - started
        if final_result is not None and getattr(final_result, "is_error", False):
            # Structured error: the CLI yielded a ResultMessage(is_error)
            # then exited 1. Classify from the structured payload; the
            # authoritative usage is still worth recording.
            failure = _structured_error_failure(
                final_result, elapsed, uncached_in + uncached_out,
            )
            u = extract_usage_tokens(final_result.usage)
            ledger_in = u.total_input or fallback_in
            ledger_out = u.output_tokens or fallback_out
            _record(ledger_in, ledger_out)
            log.error(
                "  %s ✗ failed after %.1fs — kind=%s · %s",
                spec.label, elapsed, failure.kind, failure.detail,
            )
            if spec.source is not None:
                log.error("    source:    %s", spec.source)
            if spec.model is not None:
                log.error("    model:     %s", spec.model)
            log.error(
                "    input:     %s chars (%.1f KB)",
                f"{input_chars:,}", input_chars / 1024,
            )
            log.error(
                "    tokens:    %s in / %s out burned despite failure",
                f"{uncached_in:,}", f"{uncached_out:,}",
            )
            capture.dump_to(log)
            return SdkRunResult(
                result_text=result_text,
                assistant_text="".join(text_parts),
                input_tokens=ledger_in,
                output_tokens=ledger_out,
                uncached_input_tokens=uncached_in,
                uncached_output_tokens=uncached_out,
                cost_usd=float(getattr(final_result, "total_cost_usd", 0.0) or 0.0),
                message_count=message_count,
                num_turns=final_result.num_turns,
                subtype=final_result.subtype,
                failure=failure,
                exc=exc,
                elapsed_s=elapsed,
            )
        failure = log_sdk_failure(
            log,
            label=spec.label,
            source=spec.source,
            model=spec.model,
            input_chars=input_chars,
            started=started,
            capture=capture,
            exc=exc,
            extra=spec.extra_log,
        )
        _record(fallback_in, fallback_out)
        return _partial_result(failure, exc)

    # ── clean stream end ──────────────────────────────────────────────
    elapsed = time.time() - started
    u = extract_usage_tokens(final_result.usage if final_result is not None else None)
    ledger_in = u.total_input or fallback_in
    ledger_out = u.output_tokens or fallback_out
    cost = float(final_result.total_cost_usd) if (
        final_result is not None and final_result.total_cost_usd is not None
    ) else 0.0
    failure = None
    if final_result is not None and getattr(final_result, "is_error", False):
        # Structured error with a clean generator exit (no raise) — same
        # classification as the raised variant above.
        failure = _structured_error_failure(
            final_result, elapsed, uncached_in + uncached_out,
        )
        log.error(
            "  %s ✗ failed after %.1fs — kind=%s · %s",
            spec.label, elapsed, failure.kind, failure.detail,
        )
        capture.dump_to(log)
    _record(ledger_in, ledger_out)
    return SdkRunResult(
        result_text=result_text,
        assistant_text="".join(text_parts),
        input_tokens=ledger_in,
        output_tokens=ledger_out,
        uncached_input_tokens=uncached_in,
        uncached_output_tokens=uncached_out,
        cost_usd=cost,
        message_count=message_count,
        num_turns=final_result.num_turns if final_result is not None else 0,
        subtype=final_result.subtype if final_result is not None else None,
        failure=failure,
        exc=None,
        elapsed_s=elapsed,
    )
