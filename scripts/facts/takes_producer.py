"""Extract-takes producer — post-compile pass that records third-party beliefs.

Runs after a source file's main compile output. Reads the source, asks Claude
via the Agent SDK to point at attributed beliefs (WHO believes WHAT), and
appends them to `knowledge/takes/<holder-slug>.md` via the shared
`take._append_take` helper.

Pattern mirrors `curiosity.producer.maybe_generate_curiosity_requests`, with
two important differences:

1. Provider is Claude (same as compile) — beliefs need real reasoning, not
   Ollama JSON-schema pattern-match. Per the no-silent-provider-fallback
   rule the producer never falls back to Ollama; if Claude fails, the run
   just skips this source (already-compiled output is untouched).
2. Tool surface is `Read` only — the producer reads the source and emits a
   JSON object; it does NOT write to `knowledge/takes/` directly. Writes go
   through `take._append_take` so the idempotent-line guard and the canonical
   line format stay in one place.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from core.config import CONFIG
from core.paths import ROOT_DIR, TAKES_DIR
from core.prompts import render
from core.sdk_helpers import StderrCapture, log_sdk_failure
from core.utils import today_iso

log = logging.getLogger("compile")

# Accepted by both extract_takes_source_globs and a defensive containment
# check below so the producer never accidentally runs on memories / facts /
# knowledge sources where third-party belief attribution would just collect
# the operator's own opinions back into the takes substrate.
_EXTRACT_TAKES_FORBIDDEN_PREFIXES = (
    "knowledge/",
    "raw/memories/",
    "raw/facts/",
)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` wrapping if the model emitted it despite the prompt."""
    s = text.strip()
    if s.startswith("```"):
        # Drop first fence line + trailing fence.
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


async def maybe_extract_takes(source: Path) -> None:
    """Post-compile pass: extract third-party beliefs and append to takes/<slug>.md.

    Gated by:
      - CONFIG.features.extract_takes (master switch, default False)
      - CONFIG.limits.extract_takes_source_globs (fnmatch allowlist)
      - _EXTRACT_TAKES_FORBIDDEN_PREFIXES (hard deny for cognitive self-notes)
    """
    if not CONFIG.features.extract_takes:
        return

    rel_path = str(source.relative_to(ROOT_DIR))

    # Defense-in-depth: never extract takes from self-authored material.
    if any(rel_path.startswith(p) for p in _EXTRACT_TAKES_FORBIDDEN_PREFIXES):
        return

    globs = CONFIG.limits.extract_takes_source_globs or []
    if globs and not any(fnmatch.fnmatch(rel_path, g) for g in globs):
        return

    try:
        source_content = source.read_text(encoding="utf-8")
    except OSError:
        return
    if not source_content.strip():
        return

    implicit_author = CONFIG.personal.implicit_operator_author or "(none configured)"
    prompt = render(
        "extract_takes",
        source_path=rel_path,
        source_content=source_content,
        implicit_operator_author=implicit_author,
    )

    log.info("  Takes pass for %s (model=%s)", rel_path, CONFIG.models.compile_model)

    started = time.time()
    capture = StderrCapture()
    result_text = ""
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                # Read-only: takes are appended via `take._append_take` after
                # the model emits JSON. The model does not write directly.
                allowed_tools=["Read"],
                permission_mode="default",
                max_turns=3,
                setting_sources=[],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
                break
            if isinstance(message, AssistantMessage):
                # The model may stream prose before a ResultMessage; we only
                # care about the final result, but capture the last text
                # block as a fallback for SDK builds that drop ResultMessage.
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        result_text = block.text
    except Exception as exc:  # noqa: BLE001
        log_sdk_failure(
            log,
            label="extract_takes",
            source=rel_path,
            model=CONFIG.models.compile_model,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=exc,
        )
        return

    if not result_text.strip():
        log.info("  Takes: empty model response")
        return

    cleaned = _strip_json_fences(result_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Tolerate the model wrapping the JSON in prose despite the prompt.
        # Try to locate the first `{` and parse from there.
        idx = cleaned.find("{")
        if idx < 0:
            log.warning("  Takes: model did not return JSON; first 200 chars=%r", cleaned[:200])
            return
        try:
            parsed = json.loads(cleaned[idx:])
        except json.JSONDecodeError:
            log.warning("  Takes: invalid JSON: %s", cleaned[:200])
            return

    if isinstance(parsed, list):
        takes = parsed
    elif isinstance(parsed, dict):
        takes = parsed.get("takes", [])
    else:
        log.info("  Takes: unexpected response type %s", type(parsed).__name__)
        return

    if not takes:
        log.info("  Takes: none extracted")
        return

    # Local import to dodge a circular import (take.py also imports from
    # core.paths, which is already imported above — the late binding keeps
    # the producer importable from compile.py's top-level).
    from facts.take import _append_take, VALID_CONFIDENCE

    appended = 0
    duplicates = 0
    dropped = 0
    cap = CONFIG.limits.extract_takes_max_per_source
    today = today_iso()
    for raw in takes[:cap]:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        holder = str(raw.get("holder", "")).strip()
        belief = str(raw.get("belief", "")).strip()
        confidence = str(raw.get("confidence", "")).strip().lower()
        source_field = str(raw.get("source", "")).strip() or rel_path
        if not holder or not belief or confidence not in VALID_CONFIDENCE:
            dropped += 1
            continue
        # Implicit-operator filter: drop beliefs attributed to the operator
        # themselves (those belong in facts/, not takes/).
        if (
            CONFIG.personal.implicit_operator_author
            and holder.lower() == CONFIG.personal.implicit_operator_author.lower()
        ):
            dropped += 1
            continue
        try:
            path, status = _append_take(
                holder=holder,
                belief=belief,
                confidence=confidence,
                source=source_field,
                date=today,
            )
        except ValueError:
            dropped += 1
            continue
        if status == "appended":
            appended += 1
        elif status == "duplicate":
            duplicates += 1

    log.info(
        "  Takes: %d appended, %d duplicate, %d dropped (raw=%d)",
        appended, duplicates, dropped, len(takes),
    )
