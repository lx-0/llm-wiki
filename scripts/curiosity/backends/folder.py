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
# it is not a compile source. Retarget/quarantine semantics land in T03.
NOT_ANSWERED_SENTINEL = "NOT ANSWERED IN THIS FILE"


@dataclass
class RunResult:
    success: bool
    error: str | None = None


def _resolve(root_id: str, file_path: str) -> Path | None:
    """root_id → watched_folders entry → absolute candidate path."""
    for entry in CONFIG.personal.watched_folders or []:
        if entry.get("id") == root_id and entry.get("kind") == "local":
            root = Path(os.path.expanduser(str(entry.get("path") or "")))
            return root / file_path
    return None


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

    # ── Real run: provider read → answer-only persist → request flip ──
    if not exists:
        # Stale index — fail soft without mutating the request (T03 owns
        # the quarantine/invalidation semantics).
        log.warning(
            "  Folder backend: %s MISSING (stale index?) — request %s "
            "left pending", candidate, request_path.name,
        )
        return RunResult(success=False, error=f"file missing: {candidate}")

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
        return RunResult(success=False, error=f"file missing: {exc}")

    if answer.error:
        log.warning(
            "  Folder backend: provider failed for %s — %s",
            request_path.name, answer.error,
        )
        return RunResult(success=False, error=answer.error)
    if NOT_ANSWERED_SENTINEL in answer.answer_md:
        log.info(
            "  Folder backend: %s does not answer %r — nothing persisted "
            "(request stays pending)", file_path, topic,
        )
        return RunResult(success=False, error="not_answered_in_file")

    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    slug = request_path.stem.removeprefix("request-")  # request-{slug}-{date}
    output_path = ANSWER_DIR / f"answer-{slug}.md"
    output_path.write_text(
        _render_answer(request, answer), encoding="utf-8"
    )
    log.info("  Wrote %s (answer-only, %d chars)",
             output_path, len(answer.answer_md))

    request["status"] = "done"
    request["processed_at"] = now_iso()
    request["output"] = str(output_path.relative_to(ROOT_DIR))
    request["as_of_mtime"] = answer.as_of_mtime
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    return RunResult(success=True)


def _render_answer(request: dict, answer: ScanAnswer) -> str:
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
    lines.append(f"provider: {CONFIG.models.folder_scan_provider}")
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
