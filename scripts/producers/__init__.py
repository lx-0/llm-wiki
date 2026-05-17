"""Producer subpackage — post-compile derivative-material extractors.

A Producer consumes a *compiled* knowledge source (a file under `<vault>/raw/`
that has already been turned into a wiki article by `compile.py`) and emits
derived material — suggestion notes, knowledge-gap requests, third-party
belief extractions. Mirrors Collector but operates on the opposite side of
the engine. See CONTEXT.md for the Producer / ProducerSpec / ProducerResult
/ ProducerRegistry vocabulary, and `.ytstack/backlog/producer-seam.md` for
the design that drove this module's shape.

Registration order = run order. Concrete producers (suggestions, curiosity,
takes) are imported here so their `@register` decorator fires at package
import time.
"""

from __future__ import annotations

from .base import (
    Producer,
    ProducerResult,
    ProducerSpec,
    all_producers,
    get_producer,
    register,
)

__all__ = [
    "Producer",
    "ProducerResult",
    "ProducerSpec",
    "all_producers",
    "get_producer",
    "register",
]
