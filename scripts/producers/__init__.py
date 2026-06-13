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

# Import order = run order. Today's order matches the historical await
# sequence in compile.py: suggestions → curiosity → takes; folder_curiosity
# (M027-S03) appended last. Each import triggers @register at module load.
from . import suggestions as _suggestions  # noqa: E402, F401
from . import curiosity as _curiosity  # noqa: E402, F401
from . import takes as _takes  # noqa: E402, F401
from . import folder_curiosity as _folder_curiosity  # noqa: E402, F401
from . import intents as _intents  # noqa: E402, F401

__all__ = [
    "Producer",
    "ProducerResult",
    "ProducerSpec",
    "all_producers",
    "get_producer",
    "register",
]
