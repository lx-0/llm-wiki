"""SuggestionsProducer — thin Protocol-conforming wrapper.

Delegates to the legacy free function `suggestions.producer.maybe_generate_suggestions`.
The legacy function still owns: SDK call, prompt rendering, output writing,
internal gates (today: hardcoded `_is_email_source` filter). S03 will rewire
compile.py to drive this wrapper via ProducerRegistry and lift the gate
onto Spec; until then, the wrapper is parallel to the legacy call site.

Failure contract α: any exception from the legacy fn is caught + returned as
a `failed` ProducerResult so the orchestrator's state-save is never blocked.
"""

from __future__ import annotations

import logging
from pathlib import Path

from suggestions.producer import maybe_generate_suggestions

from .base import Producer, ProducerResult, ProducerSpec, register

log = logging.getLogger(__name__)


@register
class SuggestionsProducer:
    SPEC = ProducerSpec(
        name="suggestions",
        enabled_config_key=None,
        # Forward-looking: the CONFIG key + migration land in S03. The legacy
        # function still does its own hardcoded `_is_email_source` check; the
        # orchestrator wiring will consult this key instead.
        source_glob_config_key="features.suggestions_source_globs",
    )

    async def run(self, source: Path) -> ProducerResult:
        try:
            await maybe_generate_suggestions(source)
        except Exception as exc:
            log.exception("SuggestionsProducer failed for %s", source)
            return ProducerResult(
                producer=self.SPEC.name,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return ProducerResult(producer=self.SPEC.name, status="ok")


_: Producer = SuggestionsProducer()  # structural-conformance assertion (mypy + runtime)
