"""IntentsProducer — post-compile pass that detects actionable intents.

Reads one intake source (voice note first; extend via
`CONFIG.limits.intent_source_globs`), asks Claude via the Agent SDK to classify
it into an intent `{kind, summary, confidence}` (task | idea | note | none) and
dispatches it to the handler registered for its kind (`intents.dispatch`). The
task/idea/note handlers write an operator-facing record to `workspace/inbox/`;
execution is a separate, operator-gated step (the `orchestrate-tasks` agent).
The confidence floor gates `task` only; idea/note are captured liberally.

Mirrors `facts.takes_producer` conventions:
- Provider is Claude (`models.intent_classify_model`, default a cheap tier — it's
  triage, not synthesis), no Ollama fallback. On SDK failure the source is skipped.
- Tool surface is `Read` only — the producer emits JSON; the write goes through
  the dispatched handler.

Idempotence: a per-source guard in `state/intents-seen.json` stops re-dispatch
on recompile (raw intake notes are immutable, so source path is a stable key).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from core.config import CONFIG
from core.paths import ROOT_DIR, STATE_DIR
from core.prompts import render
from core.sdk_helpers import StderrCapture, log_sdk_failure

from intents import Intent, dispatch

from .base import Producer, ProducerResult, ProducerSpec, register

log = logging.getLogger("compile")

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_SEEN_STATE = STATE_DIR / "intents-seen.json"


def _strip_json_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _load_seen() -> set[str]:
    try:
        data = json.loads(_SEEN_STATE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def _mark_seen(rel_path: str) -> None:
    seen = _load_seen()
    seen.add(rel_path)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _SEEN_STATE.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


@register
class IntentsProducer:
    SPEC = ProducerSpec(
        name="intents",
        enabled_config_key="features.extract_intents",
        source_glob_config_key="limits.intent_source_globs",
    )

    async def run(self, source: Path) -> ProducerResult:
        try:
            rel_path = str(source.resolve().relative_to(ROOT_DIR.resolve()))
        except (ValueError, OSError):
            rel_path = source.name

        if rel_path in _load_seen():
            return ProducerResult(
                producer=self.SPEC.name, status="skipped",
                reason=f"already classified: {rel_path}",
            )

        try:
            source_content = source.read_text(encoding="utf-8")
        except OSError as exc:
            return ProducerResult(
                producer=self.SPEC.name, status="failed",
                reason=f"read failed: {exc}",
            )
        if not source_content.strip():
            _mark_seen(rel_path)
            return ProducerResult(
                producer=self.SPEC.name, status="skipped", reason="empty source",
            )

        prompt = render(
            "intent_classify", source_path=rel_path, source_content=source_content,
        )
        # Intent classification is task/idea/note triage, not synthesis — a cheap
        # model suffices. Falls back to compile_model if the knob is empty.
        model = CONFIG.models.intent_classify_model or CONFIG.models.compile_model
        log.info("  Intent pass for %s (model=%s)", rel_path, model)

        started = time.time()
        capture = StderrCapture()
        result_text = ""
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                    cwd=str(ROOT_DIR),
                    model=model,
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
                    for block in message.content:
                        if hasattr(block, "text") and block.text:
                            result_text = block.text
        except Exception as exc:  # noqa: BLE001
            log_sdk_failure(
                log, label="intent_classify", source=rel_path,
                model=model, input_chars=len(source_content),
                started=started, capture=capture, exc=exc,
            )
            return ProducerResult(
                producer=self.SPEC.name, status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )

        if not result_text.strip():
            return ProducerResult(
                producer=self.SPEC.name, status="failed", reason="empty model response",
            )

        cleaned = _strip_json_fences(result_text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            idx = cleaned.find("{")
            if idx < 0:
                return ProducerResult(
                    producer=self.SPEC.name, status="failed",
                    reason=f"non-JSON response: {cleaned[:120]!r}",
                )
            try:
                parsed = json.loads(cleaned[idx:])
            except json.JSONDecodeError:
                return ProducerResult(
                    producer=self.SPEC.name, status="failed",
                    reason=f"invalid JSON: {cleaned[:120]!r}",
                )
        if not isinstance(parsed, dict):
            return ProducerResult(
                producer=self.SPEC.name, status="failed",
                reason=f"unexpected response type {type(parsed).__name__}",
            )

        kind = str(parsed.get("kind", "none")).strip().lower()
        confidence = str(parsed.get("confidence", "low")).strip().lower()
        summary = str(parsed.get("summary", "")).strip()

        # Classified — mark seen so we never re-spend on this source, regardless
        # of whether it dispatches.
        _mark_seen(rel_path)

        if kind == "none":
            return ProducerResult(
                producer=self.SPEC.name, status="ok", reason="kind=none (noise)",
            )

        # Confidence floor applies to `task` ONLY — never auto-create a task on a
        # weak signal. idea/note are low-stakes captures for the inbox, dispatched
        # regardless of confidence (the operator triages them later).
        if kind == "task":
            floor = _CONFIDENCE_RANK.get(CONFIG.limits.intent_min_confidence, 2)
            if _CONFIDENCE_RANK.get(confidence, 0) < floor:
                return ProducerResult(
                    producer=self.SPEC.name, status="ok",
                    reason=f"task below confidence floor (conf={confidence})",
                )

        intent = Intent(kind=kind, summary=summary, source=rel_path, confidence=confidence)
        try:
            res = dispatch(intent)
        except Exception as exc:  # noqa: BLE001
            log.exception("IntentsProducer dispatch failed for %s", rel_path)
            return ProducerResult(
                producer=self.SPEC.name, status="failed",
                reason=f"dispatch {type(exc).__name__}: {exc}",
            )

        return ProducerResult(
            producer=self.SPEC.name, status="ok",
            reason=f"kind={kind} → {res.status}",
            outputs=(res.output,) if res.output else (),
        )


_: Producer = IntentsProducer()
