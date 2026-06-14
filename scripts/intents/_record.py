"""Shared writer for intent records landing in `workspace/inbox/`.

task / idea / note handlers all emit the same operator-facing record shape
(frontmatter + body) into `workspace/inbox/<source-stem>.md`; only the `type:`
and the triage hint differ. Centralising the write keeps the record format in
one place and the idempotence guard (skip if the stem already exists) uniform.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.paths import WORKSPACE_INBOX_DIR
from core.utils import now_iso

from .base import HandlerResult, Intent

log = logging.getLogger("compile")


def write_inbox_record(intent: Intent, type_: str, triage_hint: str) -> HandlerResult:
    """Write one intent record into `workspace/inbox/`. Idempotent per source stem."""
    WORKSPACE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(intent.source).stem or type_
    target = WORKSPACE_INBOX_DIR / f"{stem}.md"
    if target.exists():
        return HandlerResult(
            kind=intent.kind, status="skipped",
            reason=f"inbox record already exists: {target.name}", output=target,
        )
    summary = intent.summary.strip() or "(no summary)"
    fm = (
        "---\n"
        f"type: {type_}\n"
        "status: pending\n"
        f"kind: {intent.kind}\n"
        f"confidence: {intent.confidence}\n"
        f"source: {intent.source}\n"
        f"detected_at: {now_iso()}\n"
        "---\n"
    )
    body = (
        f"# {summary}\n\n"
        f"_Detected from [[{stem}]] · {intent.kind} · confidence {intent.confidence}. "
        f"{triage_hint} Set `status: dismissed` to drop._\n\n"
        f"## {type_.capitalize()}\n\n"
        f"{summary}\n"
    )
    target.write_text(fm + body, encoding="utf-8")
    log.info("  Intent: %s record written → workspace/inbox/%s", type_, target.name)
    return HandlerResult(kind=intent.kind, status="ok", output=target)
