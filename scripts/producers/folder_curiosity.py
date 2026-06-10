"""FolderCuriosityProducer — thin Protocol-conforming wrapper.

Delegates to `curiosity.producer.maybe_generate_folder_requests` (M027-S03),
the folder sibling of the email curiosity pass. The legacy fn gates itself
on `features.curiosity_loop` AND a non-empty `personal.watched_folders` AND
existing `raw/index/` digests, so on vaults without the feature this is a
cheap no-op.

Failure contract α: any exception is caught + returned as a `failed`
ProducerResult so the orchestrator's state-save is never blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path

from curiosity.producer import maybe_generate_folder_requests

from .base import Producer, ProducerResult, ProducerSpec, register

log = logging.getLogger(__name__)


@register
class FolderCuriosityProducer:
    SPEC = ProducerSpec(
        name="folder_curiosity",
        enabled_config_key="features.curiosity_loop",
        source_glob_config_key=None,
    )

    async def run(self, source: Path) -> ProducerResult:
        try:
            await maybe_generate_folder_requests(source)
        except Exception as exc:
            log.exception("FolderCuriosityProducer failed for %s", source)
            return ProducerResult(
                producer=self.SPEC.name,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return ProducerResult(producer=self.SPEC.name, status="ok")


_: Producer = FolderCuriosityProducer()
