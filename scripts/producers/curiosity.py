"""CuriosityProducer — thin Protocol-conforming wrapper.

Delegates to the legacy free function
`curiosity.producer.maybe_generate_curiosity_requests`. Today's legacy fn
already checks `CONFIG.features.curiosity_loop` internally; the wrapper's
SPEC declares the same gate so the orchestrator (S03) can short-circuit
without the legacy fn ever entering. Until S03 lands, the internal check
stays as a defense-in-depth no-op.

Failure contract α: any exception from the legacy fn is caught + returned as
a `failed` ProducerResult so the orchestrator's state-save is never blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path

from curiosity.producer import maybe_generate_curiosity_requests

from .base import Producer, ProducerResult, ProducerSpec, register

log = logging.getLogger(__name__)


@register
class CuriosityProducer:
    SPEC = ProducerSpec(
        name="curiosity",
        enabled_config_key="features.curiosity_loop",
        source_glob_config_key=None,
    )

    async def run(self, source: Path) -> ProducerResult:
        try:
            await maybe_generate_curiosity_requests(source)
        except Exception as exc:
            log.exception("CuriosityProducer failed for %s", source)
            return ProducerResult(
                producer=self.SPEC.name,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return ProducerResult(producer=self.SPEC.name, status="ok")


_: Producer = CuriosityProducer()
