"""Analyst-agent harness for the two-pass M019 analyst layer.

Pass-1 (per-study) and Pass-2 (cross-study) share this same harness
— they differ only in which prompt-file (persona) is loaded and what
the engine inlines as context. The agent invocation, scope-lock,
cost-tracking, and error-handling are identical.

Composition (verified empirically in M019-S01-T01 + carried through
S02-T02):

  allowed_tools = ['Read', 'Glob', 'Grep']
  disallowed_tools = ['Write', 'Edit', 'NotebookEdit']
  permission_mode = 'default'
  can_use_tool = make_path_scope_gate([])  # deny-all-writes
  setting_sources = ['project']
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    UserMessage,
    query,
)

from scripts.core.sdk_helpers import (  # noqa: E402
    StderrCapture,
    log_sdk_failure,
    make_path_scope_gate,
    prompt_stream,
)


# Same composition as inference. Locked together so a single config
# tweak applies to both classes of agent.
ANALYST_ALLOWED_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")
ANALYST_DISALLOWED_TOOLS: tuple[str, ...] = ("Write", "Edit", "NotebookEdit")

# Default model — Haiku is fast + cheap. Personality post-wedge
# instruments might want Sonnet for richer interpretation; that's a
# per-call override via the `model` kwarg.
DEFAULT_ANALYST_MODEL = "claude-haiku-4-5"

# Max turns: analyst typically Reads a few substrate files (Pass-1)
# or none (Pass-2), then emits the markdown body. 8 turns leaves
# headroom for ad-hoc reads without bloat.
DEFAULT_MAX_TURNS = 8


class AnalystError(RuntimeError):
    """Raised when an analyst call fails in a way the caller must surface."""


@dataclass(frozen=True)
class AnalystResult:
    """Outcome of one analyst call (Pass-1 or Pass-2)."""

    markdown_body: str
    elapsed_ms: int
    model_id: str
    persona_version: str           # SHA256[:16] of persona prompt file
    prompt_version: str            # SHA256[:16] of full rendered prompt
    cost_usd: float
    pass_label: str                # "per-study" | "cross-study"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_analyst(
    *,
    system_prompt_path: Path,
    user_prompt: str,
    vault_cwd: Path,
    pass_label: str,
    model: str = DEFAULT_ANALYST_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> AnalystResult:
    """Run one analyst call (Pass-1 or Pass-2) end-to-end.

    Args:
        system_prompt_path: Path to `prompts/reports/analyst_per_study.md`
            or `analyst_cross_study.md`. The persona/instructions; loaded
            verbatim into the SDK call's `system_prompt`. Persona-version
            for provenance is the SHA256[:16] of this file's bytes.
        user_prompt: The "user message" the agent receives — typically
            the inlined study results, summary, and (for Pass-1) the
            prior-run summary.
        vault_cwd: Vault root the agent runs under (cwd). Read tool
            uses this as the resolution point for relative paths.
        pass_label: "per-study" or "cross-study" — recorded in the
            `AnalystResult` for provenance + logging.

    Returns:
        `AnalystResult` containing the markdown body + provenance.

    Raises:
        AnalystError: SDK failure / scope-lock violation / empty
            output. Caller surfaces to the operator + does not
            persist a half-formed `_analysis.md`.
    """
    import asyncio
    return asyncio.run(
        _run_analyst_async(
            system_prompt_path=system_prompt_path,
            user_prompt=user_prompt,
            vault_cwd=vault_cwd,
            pass_label=pass_label,
            model=model,
            max_turns=max_turns,
        )
    )


async def _run_analyst_async(
    *,
    system_prompt_path: Path,
    user_prompt: str,
    vault_cwd: Path,
    pass_label: str,
    model: str,
    max_turns: int,
) -> AnalystResult:
    log = logging.getLogger("reports.analyst")

    if not system_prompt_path.is_file():
        raise AnalystError(
            f"analyst persona prompt not found: {system_prompt_path}"
        )
    persona_text = system_prompt_path.read_text(encoding="utf-8")
    persona_version = _file_hash(system_prompt_path)
    prompt_version = _text_hash(user_prompt)

    started_wall = time.time()
    start = time.perf_counter()
    text_chunks: list[str] = []
    cost = 0.0
    capture = StderrCapture()

    options = ClaudeAgentOptions(
        cwd=str(vault_cwd),
        model=model,
        system_prompt=persona_text,
        allowed_tools=list(ANALYST_ALLOWED_TOOLS),
        disallowed_tools=list(ANALYST_DISALLOWED_TOOLS),
        permission_mode="default",
        max_turns=max_turns,
        setting_sources=["project"],
        can_use_tool=make_path_scope_gate([]),
        stderr=capture.callback,
    )

    try:
        async for message in query(
            prompt=prompt_stream(user_prompt), options=options
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if type(block).__name__ == "TextBlock":
                        text_chunks.append(getattr(block, "text", ""))
            elif isinstance(message, UserMessage):
                continue
            elif isinstance(message, ResultMessage):
                cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
    except Exception as exc:
        failure = log_sdk_failure(
            log,
            label=f"reports.analyst pass={pass_label}",
            started=started_wall,
            capture=capture,
            exc=exc,
            model=model,
            input_chars=len(user_prompt) + len(persona_text),
            extra={"persona_version": persona_version,
                   "prompt_version": prompt_version},
        )
        raise AnalystError(
            f"analyst call failed (pass={pass_label}): {failure}"
        ) from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    body = "".join(text_chunks).strip()
    if not body:
        raise AnalystError(
            f"analyst returned empty markdown body (pass={pass_label}) — "
            f"check captured stderr"
        )

    return AnalystResult(
        markdown_body=body,
        elapsed_ms=elapsed_ms,
        model_id=model,
        persona_version=persona_version,
        prompt_version=prompt_version,
        cost_usd=cost,
        pass_label=pass_label,
    )
