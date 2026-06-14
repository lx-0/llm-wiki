"""TaskHandler — routes a `task`-kind intent to an operator-facing record in
`workspace/inbox/`. The record is the queue entry the operator reviews and the
`orchestrate-tasks` agent executes. Detection (producer) and execution
(agent_task spec) stay separate; execution is operator-gated."""

from __future__ import annotations

from ._record import write_inbox_record
from .base import HandlerResult, Intent, register


@register
class TaskHandler:
    KIND = "task"

    def handle(self, intent: Intent) -> HandlerResult:
        return write_inbox_record(
            intent, "task",
            "Review, then run the `orchestrate-tasks` agent to execute.",
        )
