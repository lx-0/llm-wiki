"""Folder-deep-scan backend — S04 SKELETON (M027-S03-T03).

Mirrors `backends/email.py`'s surface so `curiosity/cli.py:_dispatch` can
route `folder-deep-scan` requests today. The actual agentic read+answer
(read the named file in-place after per-request operator approval, persist
an answer-extract to `raw/notes/folder/answer-<slug>.md`) lands in S04
behind a swappable provider seam (DECISIONS 2026-06-07).

Until then this skeleton:
- shape-checks the request and resolves `root_id` → the configured
  `personal.watched_folders` entry → absolute candidate path,
- reports whether the file still exists (stat only — the body-blind
  posture holds; doubles as a staleness signal),
- dry-run: prints what S04 WOULD do, incl. the informed-consent line,
- real run: honest not-implemented — the request file is NOT mutated
  (stays `pending` for S04), success=False.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import CONFIG
from core.paths import RAW_DIR, ROOT_DIR
from core.utils import now_iso

from .folder_providers import ScanAnswer, get_provider

log = logging.getLogger("curiosity")

# Answer artifacts land here as normal compile SOURCES (S01 answer-landing
# option (a)) — sibling of email's DEEP_SCAN_DIR. compile distils them into
# knowledge/ on its next run; this backend never writes knowledge/.
ANSWER_DIR = RAW_DIR / "notes" / "folder"

# Provider sentinel: the named file exists but does not answer the topic
# (prompts/folder_scan_answer.md contract). A non-answer is NOT persisted —
# it is not a compile source; the request is quarantined as `not-answered`.
NOT_ANSWERED_SENTINEL = "NOT ANSWERED IN THIS FILE"

# Terminal failure states (T03 quarantine). Batches never re-dispatch them
# (`list_pending` selects status=pending only); an explicit re-dispatch
# retries ONLY when the staleness gate says the source changed.
_FAIL_STATES = ("stale", "error", "not-answered")


@dataclass
class RunResult:
    success: bool
    error: str | None = None


def _resolve_entry(root_id: str) -> dict | None:
    """root_id → its `personal.watched_folders` entry (local only)."""
    for entry in CONFIG.personal.watched_folders or []:
        if entry.get("id") == root_id and entry.get("kind") == "local":
            return entry
    return None


def _resolve(root_id: str, file_path: str) -> Path | None:
    """root_id → watched_folders entry → absolute candidate path."""
    entry = _resolve_entry(root_id)
    if entry is None:
        return None
    root = Path(os.path.expanduser(str(entry.get("path") or "")))
    return root / file_path


def process_request(request_path: Path, *, dry_run: bool) -> RunResult:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return RunResult(success=False, error=f"unreadable request: {exc}")

    root_id = (request.get("root_id") or "").strip()
    file_path = (request.get("file_path") or "").strip()
    topic = (request.get("topic") or "").strip()
    if not root_id or not file_path or not topic:
        return RunResult(
            success=False,
            error="malformed folder-deep-scan request (root_id/file_path/topic)",
        )

    candidate = _resolve(root_id, file_path)
    if candidate is None:
        log.warning(
            "  Folder backend: root_id %r not in personal.watched_folders "
            "(request %s)", root_id, request_path.name,
        )
        return RunResult(success=False, error=f"unknown root_id {root_id!r}")
    exists = candidate.exists()

    if dry_run:
        log.info("  [dry-run] folder-deep-scan %s", request_path.name)
        log.info("    topic : %s", topic)
        log.info("    file  : %s (%s)", candidate,
                 "exists" if exists else "MISSING — stale index?")
        log.info(
            "    S04 would ask: file %r will be loaded and sent to the "
            "configured backend to answer %r — approve?", file_path, topic,
        )
        return RunResult(success=True)

    # ── Real run ──────────────────────────────────────────────────────
    # Re-dispatch gate (T03). Terminal states retry ONLY when the source
    # changed since the failure — an unchanged file never burns provider
    # spend twice. Dry-run above stays ungated (it is the preview).
    status = request.get("status", "pending")
    if status in ("done", "rejected"):
        return RunResult(success=False, error=f"already_{status}")
    if status == "stale" and not exists:
        return RunResult(success=False, error="still_missing")
    if status in ("error", "not-answered"):
        anchor = request.get("failed_as_of_mtime")
        if exists and anchor is not None and candidate.stat().st_mtime == anchor:
            return RunResult(success=False, error="unchanged_since_failure")
    if status not in ("pending", *_FAIL_STATES):
        return RunResult(success=False, error=f"already_{status}")

    if not exists:
        # Stale index — file gone between indexing and read. Quarantine
        # so batches stop re-dispatching; reappearance re-eligibles it.
        log.warning(
            "  Folder backend: %s MISSING (stale index?) — request %s "
            "marked stale", candidate, request_path.name,
        )
        return _mark_failed(
            request, request_path,
            status="stale", error=f"file missing: {candidate}",
        )

    provider = get_provider()
    try:
        answer: ScanAnswer = asyncio.run(
            provider.answer(
                topic=topic,
                rationale=(request.get("rationale") or "").strip(),
                file_abs=candidate,
                file_rel=file_path,
            )
        )
    except FileNotFoundError as exc:
        log.warning("  Folder backend: file vanished mid-read: %s", exc)
        return _mark_failed(
            request, request_path,
            status="stale", error=f"file missing: {exc}",
        )

    if answer.error:
        log.warning(
            "  Folder backend: provider failed for %s — %s",
            request_path.name, answer.error,
        )
        return _mark_failed(
            request, request_path,
            status="error", error=answer.error,
            failed_as_of_mtime=answer.as_of_mtime,
        )
    if NOT_ANSWERED_SENTINEL in answer.answer_md:
        log.info(
            "  Folder backend: %s does not answer %r — nothing persisted, "
            "request marked not-answered", file_path, topic,
        )
        return _mark_failed(
            request, request_path,
            status="not-answered", error="not_answered_in_file",
            failed_as_of_mtime=answer.as_of_mtime,
        )

    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    slug = request_path.stem.removeprefix("request-")  # request-{slug}-{date}
    output_path = ANSWER_DIR / f"answer-{slug}.md"
    entry = _resolve_entry(root_id) or {}
    output_path.write_text(
        _render_answer(request, answer, sensitivity=entry.get("sensitivity")),
        encoding="utf-8",
    )
    log.info("  Wrote %s (answer-only, %d chars)",
             output_path, len(answer.answer_md))

    request["status"] = "done"
    request["processed_at"] = now_iso()
    request["output"] = str(output_path.relative_to(ROOT_DIR))
    request["as_of_mtime"] = answer.as_of_mtime
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    return RunResult(success=True)


def _mark_failed(
    request: dict,
    request_path: Path,
    *,
    status: str,
    error: str,
    failed_as_of_mtime: float | None = None,
) -> RunResult:
    """Quarantine a request (email `_mark_error` template + staleness anchor).

    `failed_as_of_mtime` records the source mtime the failure happened
    against — the re-dispatch gate retries only when the file's current
    mtime differs (or, for `stale`, when the file exists again).
    """
    request["status"] = status
    request["last_error"] = error
    request["last_attempt_at"] = now_iso()
    if failed_as_of_mtime is not None:
        request["failed_as_of_mtime"] = failed_as_of_mtime
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    log.warning("  Folder backend: request %s -> %s (%s)",
                request_path.name, status, error)
    return RunResult(success=False, error=error)


def _render_answer(
    request: dict, answer: ScanAnswer, *, sensitivity: str | None = None
) -> str:
    """Answer artifact — email-deep-scan shape + S04 provenance.

    A normal compile source: frontmatter provenance (incl. the as-of
    mtime staleness tag), then the provider's distilled answer verbatim.
    NEVER the raw file body (P2 — test-pinned).
    """
    topic = request.get("topic", "")
    lines: list[str] = []
    lines.append("---")
    lines.append("type: note")
    lines.append("kind: folder-deep-scan")
    lines.append(f"topic: {json.dumps(topic, ensure_ascii=False)}")
    lines.append(f"root_id: {request.get('root_id', '')}")
    lines.append(
        f"file_path: {json.dumps(answer.file_path, ensure_ascii=False)}"
    )
    lines.append(f"as_of_mtime: {answer.as_of_mtime}")
    # Human-readable twin of the float above: the compile agent (and the
    # operator) read a date; the staleness machinery keeps the float.
    as_of_date = datetime.fromtimestamp(
        answer.as_of_mtime, tz=timezone.utc
    ).strftime("%Y-%m-%d")
    lines.append(f"as_of: {as_of_date}")
    lines.append(f"provider: {CONFIG.models.folder_scan_provider}")
    if sensitivity:
        # Q3 full build (2026-06-10): the root's tag travels with the
        # answer; compile_main propagates it onto derived articles.
        lines.append(f"sensitivity: {sensitivity}")
    lines.append('origin: "curiosity/folder-deep-scan"')
    lines.append(f"request_source: \"{request.get('source', '')}\"")
    lines.append(f"request_created: \"{request.get('created', '')}\"")
    lines.append(f'processed_at: "{now_iso()}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# Folder scan — {topic}")
    lines.append("")
    lines.append(answer.answer_md.strip())
    return "\n".join(lines) + "\n"
