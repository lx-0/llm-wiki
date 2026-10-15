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
from pathlib import Path

from .errors import swallow
from .sdk_scope import make_path_scope_gate, make_path_scope_hook, prompt_stream

# ── Stale-session env hygiene ─────────────────────────────────────────
# Hook-spawned engine processes inherit the DYING parent session's wiring
# vars (CLAUDE_CODE_SSE_PORT, CLAUDE_CODE_MESSAGING_SOCKET, …) — dead
# endpoints with no legitimate consumer in a detached process; strip the
# class defensively. NOTE (M031-S01 debugging record): this was FIRST
# suspected as the 2026-08 flush outage cause and then REFUTED by a clean
# same-input A/B — the real cause was host-MCP schema injection (see the
# strict-mcp-config block in run_sdk_query). Kept as hygiene, not as fix.
# KEPT deliberately: CLAUDE_INVOKED_BY (engine-owned marker) and all
# ANTHROPIC_* auth vars.
_STALE_SESSION_ENV_EXACT = frozenset({"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"})
_STALE_SESSION_ENV_PREFIX = "CLAUDE_CODE_"


def sanitize_stale_session_env(environ: dict) -> list[str]:
    """Remove inherited Claude-Code session-wiring vars from ``environ``
    (mutates in place). Returns the removed keys, sorted callers-side for
    logging. Idempotent; a clean env is a no-op."""
    removed = [
        key
        for key in list(environ)
        if key in _STALE_SESSION_ENV_EXACT or key.startswith(_STALE_SESSION_ENV_PREFIX)
    ]
    for key in removed:
        del environ[key]
    return removed


# Patterns matched against captured stderr + exception text + the CLI's own
# result text. Order is priority — most-specific first.
#
# cli_outdated: the API refuses a client version below a server-side floor
# ("Claude Code 2.1.97 does not support this model; version 2.1.251 or newer
# is required", error_code claude_code_version_too_old). Observed 2026-09-09
# on the lxw vault: the bundled CLI inside claude-agent-sdk 0.1.58 was
# refused for 8 days and every flush landed as `cli_crash` because the CLI
# reports API errors on STDOUT (as a ResultMessage) and the 0.1.x SDK tore
# the process down before that message reached us. Fatal: the fix is a
# newer claude-agent-sdk (`wiki update` after the engine bumps the pin).
_RE_CLI_OUTDATED = re.compile(
    r"(claude_code_version_too_old|version\s+\S+\s+or\s+newer\s+is\s+required|"
    r"does\s+not\s+support\s+this\s+model)",
    re.IGNORECASE,
)
# cli_killed: the bundled CLI died from SIGKILL (SDK reports "exit code: -9").
# Nothing inside the process writes that; the kernel did it. On macOS the
# reason is in ~/Library/Logs/DiagnosticReports/claude-*.ips — seen
# 2026-09-17 as `CODESIGNING · Taskgated Invalid Signature` because the
# vault's .venv had drifted back INTO iCloud Drive and the 200 MB binary was
# being evicted/re-materialised while mapped. Transient per call (the next
# attempt ran), so not fatal — but the detail must name the report, not
# "exited silently".
_RE_SIGKILL = re.compile(r"(exit code:\s*-9\b|\bSIGKILL\b|signal\s+9\b)", re.IGNORECASE)
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
    # `[claude-code:unrecognized_model] {"model": …}` on stderr and "There's
    # an issue with the selected model (<name>)" as the result text — the
    # shapes CLI 2.1.273 actually emits for a bad model name (probed
    # 2026-09-17); neither matched the older patterns.
    r"no.?such.?model|unrecognized.?model|issue.?with.?the.?selected.?model)",
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

    kind: str  # cli_outdated | cli_killed | rate_limit | auth | model | network | oom | cli_crash | max_turns | tokens_exceeded | unknown
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
        detail = " — " + ", ".join(f"{name} {n:,} chars" for name, n in breakdown.items())
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
    if _RE_CLI_OUTDATED.search(haystack):
        return FailureClass(
            "cli_outdated",
            "API refuses the bundled Claude CLI version — bump claude-agent-sdk "
            "in the engine, then `wiki update`",
        )
    if _RE_SIGKILL.search(haystack):
        return FailureClass(
            "cli_killed",
            "bundled CLI was SIGKILLed by the OS — on macOS read the newest "
            "~/Library/Logs/DiagnosticReports/claude-*.ips (`Code Signature "
            "Invalid` = the binary sits in an iCloud/CloudStorage path and was "
            "evicted while running; `wiki doctor` → engine-cloud-eviction)",
        )
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
            # Say what we know, not what we guess: the CLI wrote nothing to
            # stderr and no ResultMessage reached us. API-level refusals
            # (version floor, bad model, 400s) arrive as a ResultMessage on
            # stdout; when the SDK drops it, this is all that's left.
            return FailureClass(
                "cli_crash",
                f"failed in {elapsed_s:.1f}s — no result message, nothing on "
                "stderr (the CLI reports API errors on stdout; `wiki doctor` "
                "→ flush-pipeline shows the last classified cause)",
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
        label,
        elapsed,
        cls.kind,
        cls.detail,
    )
    if source is not None:
        log.error("    source:    %s", source)
    if model is not None:
        log.error("    model:     %s", model)
    if input_chars is not None:
        log.error(
            "    input:     %s chars (%.1f KB)",
            f"{input_chars:,}",
            input_chars / 1024,
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
    cli_outdated (API-side client version floor) fails identically until
    the engine ships a newer claude-agent-sdk — retrying burns 30 s sleeps
    for nothing. Rate-limit + network + cli_crash + max_turns + unknown are
    potentially transient and don't fail-fast.
    """
    return failure.kind in {"auth", "model", "tokens_exceeded", "cli_outdated"}


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

    label: str  # diagnostic label for logs
    logger: logging.Logger  # caller's logger (errors land in its *-errors.log)
    model: str | None = None
    cwd: Path | None = None
    max_turns: int | None = None
    system_prompt: str | dict | None = None
    allowed_tools: tuple[str, ...] | None = None
    disallowed_tools: tuple[str, ...] | None = None
    # BASE toolset (`--tools`). `tools=()` emits `--tools ""` → the agent
    # has NO tools at all. Distinct from `allowed_tools`, which is only an
    # allow-filter on top of the base set — and `allowed_tools=()` is falsy,
    # so the SDK transport skips the flag and the DEFAULT toolset stays
    # active (KNOWLEDGE "to disable tools use tools=[]"). Text-in/text-out
    # sites (flush, lint contradictions) want this one.
    tools: tuple[str, ...] | None = None
    permission_mode: str | None = None
    setting_sources: tuple[str, ...] | None = None
    write_scope: WriteScope | None = None  # hook-gated Write/Edit path scope
    deny_all_writes: bool = False  # read-only wedge (M019): can_use_tool deny-all
    stall_timeout_s: float | None = None  # per-MESSAGE stall timeout, not wall-clock
    source: str | None = None  # provenance string for failure logs
    input_chars: int | None = None  # defaults to len(prompt)
    extra_log: dict | None = None  # extra key/values for log_sdk_failure
    record_usage: bool = True  # LEDGER.record on every outcome


@dataclass(frozen=True)
class SdkRunResult:
    """Typed outcome of one ``run_sdk_query`` call.

    ``failure is None`` means the stream completed without an SDK-level
    error. ``input_tokens``/``output_tokens`` are the cache-inclusive
    totals (the LEDGER basis); ``uncached_*`` are the raw per-turn sums
    (the runaway-budget basis) — see DECISIONS 2026-06-02.
    """

    result_text: str = ""  # ResultMessage.result (final agent text)
    assistant_text: str = ""  # concatenated AssistantMessage TextBlocks
    input_tokens: int = 0  # cache-inclusive true input (LEDGER basis)
    output_tokens: int = 0
    uncached_input_tokens: int = 0  # raw per-turn sum (budget-guard basis)
    uncached_output_tokens: int = 0
    cost_usd: float = 0.0  # SDK-reported actual (ResultMessage.total_cost_usd)
    message_count: int = 0
    num_turns: int = 0
    subtype: str | None = None  # ResultMessage.subtype when one arrived
    failure: FailureClass | None = None
    exc: BaseException | None = None  # original exception for `raise ... from`
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.failure is None


_RESULT_EXCERPT_CHARS = 240


def _structured_error_failure(
    final_result,
    elapsed_s: float,
    uncached_tokens: int,
    stderr_text: str = "",
) -> FailureClass:
    """FailureClass for a structured ``ResultMessage(is_error=True)``.

    ``error_max_turns`` maps to kind=max_turns; everything else routes
    through the shared classifier over the result text, the SDK's
    ``errors`` list AND the captured stderr, so a fast empty-stderr fail
    lands as cli_crash and a slow no-signal fail as unknown (which retry
    ladders treat differently from an opaque agent_error).

    The result text IS the API's error message ("API Error: 400 {…}",
    "There's an issue with the selected model …") — the CLI reports it as
    a ResultMessage, not on stderr. It goes into the detail verbatim
    (excerpted) so the *-errors.log line names the cause instead of
    "success after 1 turns". Lesson of the 2026-09-09→17 outage.
    """
    errors = getattr(final_result, "errors", None) or []
    result_text = final_result.result or ""
    if final_result.subtype == "error_max_turns":
        kind = "max_turns"
    else:
        kind = classify_failure(
            elapsed_s,
            f"{result_text}\n{stderr_text}",
            "; ".join(errors),
        ).kind
    detail = (
        f"{final_result.subtype} after {final_result.num_turns} turns "
        f"({elapsed_s:.1f}s, {uncached_tokens:,} tok)"
    )
    if errors:
        detail += f" — errors: {'; '.join(errors)}"
    excerpt = " ".join(result_text.split())
    if excerpt:
        if len(excerpt) > _RESULT_EXCERPT_CHARS:
            excerpt = excerpt[:_RESULT_EXCERPT_CHARS] + "…"
        detail += f" — result: {excerpt}"
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
    import os

    removed_env = sanitize_stale_session_env(os.environ)  # type: ignore[arg-type]
    if removed_env:
        spec.logger.debug(
            "stripped stale session env before SDK spawn: %s", ", ".join(sorted(removed_env))
        )

    if query_fn is None:
        from claude_agent_sdk import query as _sdk_query

        query_fn = _sdk_query

    capture = StderrCapture()
    started = time.time()
    input_chars = spec.input_chars if spec.input_chars is not None else len(prompt)
    timeout = spec.stall_timeout_s if (spec.stall_timeout_s or 0) > 0 else None
    options, query_prompt = _build_options(spec, prompt, capture)
    state = _StreamState()
    agen = None
    try:
        agen = query_fn(prompt=query_prompt, options=options).__aiter__()
        await _consume_stream(agen, state, timeout=timeout)
    except TimeoutError:
        return await _timeout_result(
            spec,
            state,
            agen,
            started=started,
            timeout=timeout,
            input_chars=input_chars,
            capture=capture,
        )
    except Exception as exc:
        return _failed_stream_result(
            spec, state, exc, started=started, input_chars=input_chars, capture=capture
        )
    return _clean_end_result(spec, state, started=started, capture=capture)


def _build_options(spec: SdkCallSpec, prompt: str, capture: StderrCapture) -> tuple[object, object]:
    """``ClaudeAgentOptions`` for one call plus the prompt to pass (a stream under
    the deny-all gate): buffer size from CONFIG, stderr capture wired, the write
    gating — ``spec.write_scope`` → PreToolUse path-scope hook (production,
    2026-05-18) or the legacy glob shape when the ``compile_callback_gate`` flag
    is off; ``spec.deny_all_writes`` → ``can_use_tool`` deny-all gate + streaming
    prompt (the callback contract requires an AsyncIterable prompt) — and the
    host-MCP isolation."""
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    from .config import CONFIG

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
    if spec.tools is not None:
        options_kwargs["tools"] = list(spec.tools)

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
        if scope.legacy_allowed_tools is not None and not CONFIG.features.compile_callback_gate:
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
                        hooks=[
                            make_path_scope_hook(
                                list(scope.roots),
                                denied_subpaths=list(scope.denied_subpaths) or None,
                            )
                        ],
                    ),
                ],
            }
            options_kwargs["permission_mode"] = spec.permission_mode or "default"
    else:
        if spec.allowed_tools is not None:
            options_kwargs["allowed_tools"] = list(spec.allowed_tools)
        if spec.permission_mode is not None:
            options_kwargs["permission_mode"] = spec.permission_mode

    # Engine SDK calls NEVER want the HOST's MCP servers (substrate-is-subject
    # discipline — and the M031-S01 root cause: a host MCP server shipping a
    # top-level oneOf/allOf/anyOf schema turned every request into an API 400
    # → silent CLI exit 1). strict-mcp-config makes the CLI use ONLY the MCP
    # config passed explicitly (none, unless a spec sets one).
    options_kwargs.setdefault("mcp_servers", {})
    extra = dict(options_kwargs.get("extra_args") or {})
    extra.setdefault("strict-mcp-config", None)
    options_kwargs["extra_args"] = extra

    return ClaudeAgentOptions(**options_kwargs), query_prompt


@dataclass
class _StreamState:
    """What the message loop accumulates — the input of every ending."""

    uncached_in: int = 0  # raw per-turn sums (budget basis)
    uncached_out: int = 0
    fallback_in: int = 0  # cache-inclusive per-turn fallback
    fallback_out: int = 0
    text_parts: list[str] = field(default_factory=list)
    final_result: object = None
    result_text: str = ""
    message_count: int = 0

    @property
    def assistant_text(self) -> str:
        return "".join(self.text_parts)


async def _consume_stream(agen, state: _StreamState, *, timeout: float | None) -> None:
    """The one message loop: the per-message stall timeout (a bundled-CLI hang
    surfaces as TimeoutError instead of blocking forever), usage on both bases,
    the assistant text, the final ResultMessage. Raises what the stream raises —
    the caller picks the ending."""
    import asyncio

    from claude_agent_sdk import AssistantMessage, ResultMessage

    while True:
        try:
            if timeout is not None:
                message = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
            else:
                message = await agen.__anext__()
        except StopAsyncIteration:
            break
        state.message_count += 1
        if isinstance(message, AssistantMessage):
            usage = getattr(message, "usage", None)
            if usage:
                u = extract_usage_tokens(usage)
                state.uncached_in += u.input_tokens
                state.uncached_out += u.output_tokens
                state.fallback_in += u.total_input
                state.fallback_out += u.output_tokens
            for block in getattr(message, "content", None) or ():
                if type(block).__name__ == "TextBlock":
                    state.text_parts.append(getattr(block, "text", ""))
        elif isinstance(message, ResultMessage):
            state.final_result = message
            state.result_text = message.result or ""


def _record_usage(spec: SdkCallSpec, input_tokens: int, output_tokens: int) -> None:
    """LEDGER gets the cache-inclusive totals on EVERY outcome — partial usage
    from a failed call is still real spend. Late import: tests swap
    ``core.usage.LEDGER`` and must see it at call time."""
    if spec.record_usage:
        from .usage import LEDGER, PROVIDER_CLAUDE

        LEDGER.record(
            model=spec.model or "(default)",
            provider=PROVIDER_CLAUDE,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _partial_result(
    state: _StreamState, failure: FailureClass, exc: BaseException | None, *, started: float
) -> SdkRunResult:
    """The result of a call that did not reach a clean end: the per-turn
    fallback totals, no SDK cost, whatever the ResultMessage said so far."""
    fr = state.final_result
    return SdkRunResult(
        result_text=state.result_text,
        assistant_text=state.assistant_text,
        input_tokens=state.fallback_in,
        output_tokens=state.fallback_out,
        uncached_input_tokens=state.uncached_in,
        uncached_output_tokens=state.uncached_out,
        cost_usd=0.0,
        message_count=state.message_count,
        num_turns=fr.num_turns if fr is not None else 0,
        subtype=fr.subtype if fr is not None else None,
        failure=failure,
        exc=exc,
        elapsed_s=time.time() - started,
    )


async def _timeout_result(
    spec: SdkCallSpec,
    state: _StreamState,
    agen,
    *,
    started: float,
    timeout: float | None,
    input_chars: int,
    capture: StderrCapture,
) -> SdkRunResult:
    """The stall ending: the bundled CLI hung — warn, close the stream
    best-effort, diagnose, record the partial usage, return kind=timeout."""
    log = spec.logger
    elapsed = time.time() - started
    log.warning(
        "  %s ⏱ per-call timeout after %.1fs (no message for %ss, "
        "messages so far=%d) — bundled CLI hung. model=%s source=%s (%s chars).",
        spec.label,
        elapsed,
        timeout,
        state.message_count,
        spec.model or "(default)",
        spec.source or "—",
        f"{input_chars:,}",
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
        exc=TimeoutError(f"per-call timeout after {elapsed:.1f}s (stall_timeout_s={timeout})"),
        extra=spec.extra_log,
    )
    _record_usage(spec, state.fallback_in, state.fallback_out)
    return _partial_result(
        state,
        FailureClass(
            "timeout",
            f"per-call stall after {elapsed:.1f}s (messages={state.message_count})",
        ),
        None,
        started=started,
    )


def _failed_stream_result(
    spec: SdkCallSpec,
    state: _StreamState,
    exc: Exception,
    *,
    started: float,
    input_chars: int,
    capture: StderrCapture,
) -> SdkRunResult:
    """The raised ending. A structured error — the CLI yielded a
    ResultMessage(is_error) then exited 1 — is classified from the structured
    payload with the authoritative usage recorded; anything else is a crash
    diagnosed by ``log_sdk_failure``."""
    log = spec.logger
    elapsed = time.time() - started
    fr = state.final_result
    if fr is not None and getattr(fr, "is_error", False):
        failure = _structured_error_failure(
            fr,
            elapsed,
            state.uncached_in + state.uncached_out,
            capture.text,
        )
        u = extract_usage_tokens(fr.usage)
        ledger_in = u.total_input or state.fallback_in
        ledger_out = u.output_tokens or state.fallback_out
        _record_usage(spec, ledger_in, ledger_out)
        log.error(
            "  %s ✗ failed after %.1fs — kind=%s · %s",
            spec.label,
            elapsed,
            failure.kind,
            failure.detail,
        )
        if spec.source is not None:
            log.error("    source:    %s", spec.source)
        if spec.model is not None:
            log.error("    model:     %s", spec.model)
        log.error(
            "    input:     %s chars (%.1f KB)",
            f"{input_chars:,}",
            input_chars / 1024,
        )
        log.error(
            "    tokens:    %s in / %s out burned despite failure",
            f"{state.uncached_in:,}",
            f"{state.uncached_out:,}",
        )
        capture.dump_to(log)
        return SdkRunResult(
            result_text=state.result_text,
            assistant_text=state.assistant_text,
            input_tokens=ledger_in,
            output_tokens=ledger_out,
            uncached_input_tokens=state.uncached_in,
            uncached_output_tokens=state.uncached_out,
            cost_usd=float(getattr(fr, "total_cost_usd", 0.0) or 0.0),
            message_count=state.message_count,
            num_turns=fr.num_turns,
            subtype=fr.subtype,
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
    _record_usage(spec, state.fallback_in, state.fallback_out)
    return _partial_result(state, failure, exc, started=started)


def _clean_end_result(
    spec: SdkCallSpec, state: _StreamState, *, started: float, capture: StderrCapture
) -> SdkRunResult:
    """The clean ending: usage from the ResultMessage (the per-turn sums as
    fallback), the SDK's cost, and — when the ResultMessage says is_error with
    a clean generator exit — the same classification as the raised variant."""
    log = spec.logger
    elapsed = time.time() - started
    fr = state.final_result
    u = extract_usage_tokens(fr.usage if fr is not None else None)
    ledger_in = u.total_input or state.fallback_in
    ledger_out = u.output_tokens or state.fallback_out
    cost = float(fr.total_cost_usd) if (fr is not None and fr.total_cost_usd is not None) else 0.0
    failure = None
    if fr is not None and getattr(fr, "is_error", False):
        failure = _structured_error_failure(
            fr,
            elapsed,
            state.uncached_in + state.uncached_out,
            capture.text,
        )
        log.error(
            "  %s ✗ failed after %.1fs — kind=%s · %s",
            spec.label,
            elapsed,
            failure.kind,
            failure.detail,
        )
        capture.dump_to(log)
    _record_usage(spec, ledger_in, ledger_out)
    return SdkRunResult(
        result_text=state.result_text,
        assistant_text=state.assistant_text,
        input_tokens=ledger_in,
        output_tokens=ledger_out,
        uncached_input_tokens=state.uncached_in,
        uncached_output_tokens=state.uncached_out,
        cost_usd=cost,
        message_count=state.message_count,
        num_turns=fr.num_turns if fr is not None else 0,
        subtype=fr.subtype if fr is not None else None,
        failure=failure,
        exc=None,
        elapsed_s=elapsed,
    )
