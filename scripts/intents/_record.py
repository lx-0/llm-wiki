"""Shared writer for intent records landing in `workspace/inbox/`.

task / idea / note handlers all emit the same operator-facing record shape
(frontmatter + body) into `workspace/inbox/<source-stem>.md`; only the `type:`
and the triage hint differ. Centralising the write keeps the record format in
one place and the idempotence guard (skip if the stem already exists) uniform.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core import frontmatter
from core.paths import WORKSPACE_INBOX_DIR
from core.utils import now_iso

from .base import HandlerResult, Intent

log = logging.getLogger("compile")


def write_inbox_record(intent: Intent, type_: str, triage_hint: str) -> HandlerResult:
    """Write one intent record into `workspace/inbox/`. Idempotent per source stem.

    The record goes through `core.frontmatter` — the same grammar `wiki triage`
    reads back — so summaries with umlauts/quotes round-trip exactly (C03; the
    old json.dumps write garbled them on the CLI read side). Collapsed to one
    line because every frontmatter reader here is line-oriented (triage CLI,
    templates/triage.html, desktop Triage).
    """
    WORKSPACE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(intent.source).stem or type_
    target = WORKSPACE_INBOX_DIR / f"{stem}.md"
    if target.exists():
        return HandlerResult(
            kind=intent.kind, status="skipped",
            reason=f"inbox record already exists: {target.name}", output=target,
        )
    summary = " ".join(intent.summary.split()) or "(no summary)"
    fm = {
        "type": type_,
        "status": "pending",
        "kind": intent.kind,
        "confidence": intent.confidence,
        "summary": summary,
        "source": intent.source,
        "detected_at": now_iso(),
    }
    body = (
        f"# {summary}\n\n"
        f"_Detected from [[{stem}]] · {intent.kind} · confidence {intent.confidence}. "
        f"{triage_hint} Set `status: dismissed` to drop._\n\n"
        f"## {type_.capitalize()}\n\n"
        f"{summary}\n"
    )
    frontmatter.write(target, fm, body)
    log.info("  Intent: %s record written → workspace/inbox/%s", type_, target.name)
    return HandlerResult(kind=intent.kind, status="ok", output=target)
