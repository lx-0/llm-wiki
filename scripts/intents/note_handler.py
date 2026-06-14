"""NoteHandler — routes a `note`-kind intent (a reference / fact-to-keep with no
open loop) to a record in `workspace/inbox/`. A pure reference note is
semantic, not operational, so triage promotes it to `knowledge/` — but the
engine never auto-writes knowledge/ (compile-owned); it lands in the inbox for
the operator (or the orchestrator) to promote."""

from __future__ import annotations

from ._record import write_inbox_record
from .base import HandlerResult, Intent, register


@register
class NoteHandler:
    KIND = "note"

    def handle(self, intent: Intent) -> HandlerResult:
        return write_inbox_record(
            intent, "note",
            "A reference note — promote it to knowledge/ or keep for reference.",
        )
