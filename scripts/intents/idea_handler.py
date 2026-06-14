"""IdeaHandler — routes an `idea`-kind intent (a thought / question / "would it
make sense?" capture, not yet actionable) to a record in `workspace/inbox/`.
GTD "incubate / someday-maybe": kept as an operational loop until the operator
promotes it (to a project/concept) or dismisses it."""

from __future__ import annotations

from ._record import write_inbox_record
from .base import HandlerResult, Intent, register


@register
class IdeaHandler:
    KIND = "idea"

    def handle(self, intent: Intent) -> HandlerResult:
        return write_inbox_record(
            intent, "idea",
            "An idea to incubate — promote it to a project/concept when ready.",
        )
