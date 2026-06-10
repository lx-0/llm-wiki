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

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from core.config import CONFIG

log = logging.getLogger("curiosity")


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

    log.info(
        "  Folder backend lands in S04 — request %s left pending "
        "(file %s, %s)", request_path.name, candidate,
        "exists" if exists else "MISSING",
    )
    return RunResult(
        success=False, error="folder backend not implemented (S04)"
    )
