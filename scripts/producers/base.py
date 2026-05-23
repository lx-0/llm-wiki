"""Producer base — post-compile-shaped registration + Protocol + Registry.

Mirrors `scripts/collectors/base.py`. A Producer consumes a compiled source
(under `<vault>/raw/`) and emits derived material (suggestion notes, knowledge-
gap requests, third-party belief extractions). The orchestrator (compile.py's
post-pass loop) evaluates Spec gates + wraps `run()` in try/except, so
producer bodies stay thin and uniform.

Registration order = run order, preserved across re-imports. The Registry is
consumed by:
- `compile.py`'s post-pass loop to discover producers at runtime
- `wiki produce <name>` CLI to dispatch operator-invoked re-runs

See CONTEXT.md for the Producer vocabulary and `.ytstack/backlog/producer-seam.md`
for the design that drove this shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol, runtime_checkable


# ── Spec ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProducerSpec:
    """Static declaration on each Producer class.

    Both gate fields are **dotted CONFIG paths** evaluated by the
    orchestrator, never by the Producer body. This removes the in-method
    gate-check duplication that the legacy `maybe_X(source)` functions
    carried.
    """

    name: str
    """Producer identity. Becomes the CLI argument: `wiki produce takes`."""

    enabled_config_key: str | None
    """Dotted path into CONFIG that must be truthy for the Producer to run
    (e.g. ``"features.extract_takes"``). ``None`` = always enabled.
    """

    source_glob_config_key: str | None
    """Dotted path into CONFIG resolving to a ``list[str]`` of fnmatch
    patterns. The source path (relative to vault root) must match at least
    one pattern. ``None`` = applies to every source.
    """


# ── Result type ──────────────────────────────────────────────────────


ProducerStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class ProducerResult:
    """What `Producer.run()` returns.

    Replaces the legacy `None`-returning shape so per-source aggregation,
    cost reporting, and end-of-run summaries become possible.

    Failure contract α: a ``failed`` result NEVER blocks the compile-source
    state save. The orchestrator records the failure, surfaces it in logs +
    end-of-run summary, and proceeds. See `.ytstack/backlog/producer-seam.md`.
    """

    producer: str  # SPEC.name
    status: ProducerStatus
    reason: str | None = None
    outputs: tuple[Path, ...] = ()


# ── Producer Protocol ────────────────────────────────────────────────


@runtime_checkable
class Producer(Protocol):
    """Each Producer reads a compiled source and emits derived material.

    Spec gates (``enabled_config_key`` + ``source_glob_config_key``) are
    evaluated by the orchestrator BEFORE calling ``run()``. Producers do
    not duplicate gate-check code internally.
    """

    SPEC: ClassVar[ProducerSpec]

    async def run(self, source: Path) -> ProducerResult:
        """Execute one post-pass for ``source``.

        Returns a ``ProducerResult``. Producers MAY raise — the orchestrator
        wraps + classifies the failure into a ``failed`` ProducerResult.
        Producers SHOULD prefer returning a ``failed`` result with a
        descriptive ``reason`` over raising, when the failure is anticipated
        (e.g. LLM timeout, schema validation).
        """
        ...


# ── Registry ─────────────────────────────────────────────────────────


_PRODUCERS: dict[str, type[Producer]] = {}


def register(cls: type[Producer]) -> type[Producer]:
    """Decorator. Auto-registers a Producer class in the Registry.

    Usage::

        @register
        class TakesProducer:
            SPEC = ProducerSpec(name="takes", ...)
            async def run(self, source: Path) -> ProducerResult: ...

    Importing the module that defines the class triggers registration.
    `producers/__init__.py` imports each submodule for this reason.

    Same-class re-registration is a no-op (handles the
    ``__main__ ↔ producers.<name>`` double-load when a module is run
    directly). Different classes claiming the same SPEC.name is an error.
    """
    if not hasattr(cls, "SPEC"):
        raise TypeError(
            f"@register: {cls.__name__} must define a SPEC class attribute "
            "(ProducerSpec instance)."
        )
    spec = cls.SPEC  # type: ignore[attr-defined]
    if spec.name in _PRODUCERS:
        existing = _PRODUCERS[spec.name]
        if existing.__qualname__ == cls.__qualname__:
            return cls
        raise ValueError(
            f"@register: producer name {spec.name!r} already registered "
            f"by {existing.__name__}; would overwrite with {cls.__name__}."
        )
    _PRODUCERS[spec.name] = cls
    return cls


def all_producers() -> list[Producer]:
    """Yield instantiated producers in registration order.

    Run order = registration order. Today: suggestions → curiosity → takes
    (matches the historical await sequence in compile.py).
    """
    return [cls() for cls in _PRODUCERS.values()]


def get_producer(name: str) -> Producer | None:
    """Resolve a producer by SPEC.name. Returns None if not registered."""
    cls = _PRODUCERS.get(name)
    return cls() if cls is not None else None
