"""TakesProducer — thin Protocol-conforming wrapper.

Delegates to the legacy free function `facts.takes_producer.maybe_extract_takes`.
The legacy fn already checks `CONFIG.features.extract_takes` and the source-
glob allowlist `CONFIG.limits.extract_takes_source_globs` internally. The
wrapper's SPEC declares both so the orchestrator (S03) can short-circuit
without entering the legacy fn. Until S03 the internal checks stay as a
defense-in-depth no-op.

Failure contract α: any exception from the legacy fn is caught + returned as
a `failed` ProducerResult so the orchestrator's state-save is never blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path

from facts.takes_producer import maybe_extract_takes

from .base import Producer, ProducerResult, ProducerSpec, register

log = logging.getLogger(__name__)


@register
class TakesProducer:
    SPEC = ProducerSpec(
        name="takes",
        enabled_config_key="features.extract_takes",
        source_glob_config_key="limits.extract_takes_source_globs",
    )

    async def run(self, source: Path) -> ProducerResult:
        try:
            await maybe_extract_takes(source)
        except Exception as exc:
            log.exception("TakesProducer failed for %s", source)
            return ProducerResult(
                producer=self.SPEC.name,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return ProducerResult(producer=self.SPEC.name, status="ok")


_: Producer = TakesProducer()
