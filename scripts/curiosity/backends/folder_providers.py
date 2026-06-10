"""Folder-scan answer providers — the Q9 seam (M027-S04-T01).

The curiosity folder backend reads ONE operator-approved file in-place and
distills a topic-focused answer-extract (never the raw body — P2). The
read+answer step sits behind a config-selected provider so the engine can
swap Claude SDK for a local LLM/agent later with the same request/answer
contract (DECISIONS 2026-06-07). Selection is explicit:
`CONFIG.models.folder_scan_provider`; an unknown name raises ConfigError —
never a silent fallback (`feedback_no_silent_provider_fallback`).

The Claude provider is deliberately tighter-sandboxed than compile/dream:
`allowed_tools=["Read"]` ONLY (no Write/Edit/Glob/Grep — the agent reads
exactly the named file; persistence happens Python-side in the backend),
with a PreToolUse `make_path_scope_hook([file_abs])` exact-file scope
(file-as-root, operations-log precedent) and `cwd` pinned to the file's
parent. Hook path, not `can_use_tool` — see KNOWLEDGE.md on the silent
write-failure incident.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    query,
)

from core.config import CONFIG, ConfigError
from core.prompts import render
from core.sdk_helpers import (
    StderrCapture,
    extract_usage_tokens,
    log_sdk_failure,
    make_path_scope_hook,
)

log = logging.getLogger("curiosity")

_MAX_TURNS = 6  # one named file, read + answer — no fan-out


@dataclass
class ScanAnswer:
    """The provider contract's return value (same for every provider)."""

    answer_md: str  # distilled, topic-focused markdown — NEVER the raw body
    file_path: str  # rel_path the answer was extracted from
    as_of_mtime: float  # stat'd at read time — staleness carry (T02/T03)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None  # provider-level failure; None = success


class FolderScanProvider(Protocol):
    async def answer(
        self, *, topic: str, rationale: str, file_abs: Path, file_rel: str
    ) -> ScanAnswer: ...


class ClaudeSdkProvider:
    """Claude SDK agentic read — today's only provider."""

    async def answer(
        self, *, topic: str, rationale: str, file_abs: Path, file_rel: str
    ) -> ScanAnswer:
        # stat BEFORE the read: as-of anchor for staleness invalidation.
        # FileNotFoundError propagates — quarantine semantics are the
        # backend's (T03), not the provider's.
        as_of_mtime = file_abs.stat().st_mtime

        prompt = render(
            "folder_scan_answer",
            topic=topic,
            rationale=rationale,
            file_rel=file_rel,
            file_abs=str(file_abs),
        )
        capture = StderrCapture()
        options = ClaudeAgentOptions(
            cwd=str(file_abs.parent),
            model=CONFIG.models.compile_model,
            max_turns=_MAX_TURNS,
            system_prompt=render("folder_scan_answer_system"),
            allowed_tools=["Read"],
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="Read",
                        hooks=[make_path_scope_hook([file_abs])],
                    ),
                ],
            },
            permission_mode="default",
            stderr=capture.callback,
        )

        started = time.time()
        result_text = ""
        final: ResultMessage | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    final = message
                    result_text = message.result or ""
        except Exception as exc:  # noqa: BLE001 — provider-level fail-soft
            log_sdk_failure(
                log,
                label="folder-scan",
                started=started,
                capture=capture,
                exc=exc,
                source=file_rel,
                model=CONFIG.models.compile_model,
            )
            return ScanAnswer(
                answer_md="",
                file_path=file_rel,
                as_of_mtime=as_of_mtime,
                error=f"{type(exc).__name__}: {exc}",
            )

        tokens = extract_usage_tokens(final.usage if final else None)
        if not result_text.strip():
            return ScanAnswer(
                answer_md="",
                file_path=file_rel,
                as_of_mtime=as_of_mtime,
                input_tokens=tokens.total_input,
                output_tokens=tokens.output_tokens,
                error="empty_result",
            )
        return ScanAnswer(
            answer_md=result_text,
            file_path=file_rel,
            as_of_mtime=as_of_mtime,
            input_tokens=tokens.total_input,
            output_tokens=tokens.output_tokens,
        )


_PROVIDERS: dict[str, type] = {
    "claude-sdk": ClaudeSdkProvider,
}


def get_provider() -> FolderScanProvider:
    """Resolve the configured provider — loud on unknown names."""
    name = CONFIG.models.folder_scan_provider
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ConfigError(
            f"models.folder_scan_provider={name!r} is not a known provider "
            f"(known: {sorted(_PROVIDERS)}). No silent fallback — fix the "
            "config."
        )
    return cls()
