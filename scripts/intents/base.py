"""Intent-dispatch base — Intent record + Handler Protocol + Registry.

Mirrors `producers/base.py`. The `intents` producer classifies an intake note
into an `Intent` and dispatches it to the handler registered for its `kind`.
Each handler owns its outcome destination (the `task` handler writes an
operator-facing record to `tasks/`; future handlers — fact / research / idea —
route elsewhere). The seam is open for extension: a new outcome kind is one new
handler module, registered, with no change to the producer or sibling handlers.

Registration is keyed by `Handler.KIND`. Importing a handler module triggers
its `@register`. `intents/__init__.py` imports each handler for this reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable


@dataclass(frozen=True)
class Intent:
    """One classified intent extracted from an intake note.

    `kind` selects the handler. `source` is the vault-relative path to the
    canonical raw note (provenance). `extra` carries handler-specific payload
    a future classifier might add without changing this dataclass.
    """

    kind: str
    summary: str
    source: str
    confidence: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HandlerResult:
    """What a handler returns. `output` is the artifact it wrote (if any)."""

    kind: str
    status: str  # "ok" | "skipped" | "failed"
    reason: str | None = None
    output: Path | None = None


@runtime_checkable
class IntentHandler(Protocol):
    """Routes one `Intent` of a specific `KIND` to its outcome."""

    KIND: ClassVar[str]

    def handle(self, intent: Intent) -> HandlerResult: ...


_HANDLERS: dict[str, type[IntentHandler]] = {}


def register(cls: type[IntentHandler]) -> type[IntentHandler]:
    """Decorator. Auto-registers a handler class by its `KIND`.

    Same-class re-registration is a no-op (handles the
    `__main__ ↔ intents.<name>` double-load). Two classes claiming the same
    KIND is an error.
    """
    if not hasattr(cls, "KIND"):
        raise TypeError(f"@register: {cls.__name__} must define a KIND class attribute.")
    kind = cls.KIND
    if kind in _HANDLERS:
        existing = _HANDLERS[kind]
        if existing.__qualname__ == cls.__qualname__:
            return cls
        raise ValueError(
            f"@register: intent kind {kind!r} already registered by "
            f"{existing.__name__}; would overwrite with {cls.__name__}."
        )
    _HANDLERS[kind] = cls
    return cls


def get_handler(kind: str) -> IntentHandler | None:
    """Resolve a handler by KIND. Returns None if no handler is registered."""
    cls = _HANDLERS.get(kind)
    return cls() if cls is not None else None
