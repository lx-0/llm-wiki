"""TaskHandler — routes a `task`-kind intent to an operator-facing record.

Writes `tasks/<source-stem>.md` with `status: pending` frontmatter. The file
is the queue entry the operator reviews and the `orchestrate-tasks` agent
spec executes. It does NOT run the task — detection (producer) and execution
(agent_task spec) stay separate, and execution is operator-gated.

Filename is derived from the source note's stem (already timestamped + slugged
for voice notes, e.g. `voice-2026-06-12-2212-…`), so a re-dispatch of the same
source is idempotent: an existing record is left untouched rather than
duplicated.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.paths import TASKS_DIR
from core.utils import now_iso

from .base import HandlerResult, Intent, register

log = logging.getLogger("compile")


@register
class TaskHandler:
    KIND = "task"

    def handle(self, intent: Intent) -> HandlerResult:
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(intent.source).stem or "task"
        target = TASKS_DIR / f"{stem}.md"
        if target.exists():
            return HandlerResult(
                kind=self.KIND, status="skipped",
                reason=f"task record already exists: {target.name}", output=target,
            )

        summary = intent.summary.strip() or "(no summary)"
        # Block-scalar the summary defensively in case it carries a colon/quote.
        fm = (
            "---\n"
            "type: task\n"
            "status: pending\n"
            f"kind: {intent.kind}\n"
            f"confidence: {intent.confidence}\n"
            f"source: {intent.source}\n"
            f"detected_at: {now_iso()}\n"
            "---\n"
        )
        body = (
            f"# {summary}\n\n"
            f"_Detected from [[{stem}]] · confidence {intent.confidence}. "
            "Review, then run the `orchestrate-tasks` agent to execute. "
            "Set `status: dismissed` to skip._\n\n"
            "## Task\n\n"
            f"{summary}\n"
        )
        target.write_text(fm + body, encoding="utf-8")
        log.info("  Intent: task record written → tasks/%s", target.name)
        return HandlerResult(kind=self.KIND, status="ok", output=target)
