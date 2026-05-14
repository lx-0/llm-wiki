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

    kind: str   # rate_limit | auth | model | network | oom | cli_crash | unknown
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
    Rate-limit + network + cli_crash + unknown are potentially transient.
    """
    return failure.kind in {"auth", "model"}
