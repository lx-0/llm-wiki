"""Post-pass stage of the compile pipeline (M018-S04).

``run_post_passes(source_path, compile_result, state) → list[ProducerResult]``
owns the per-file post-pass loop that Phase 1 (commit ``e730d26``) wired
inline into ``compile.py:main()``. It iterates ``ProducerRegistry.all_producers()``
in registration order (suggestions → curiosity → takes) and calls the
already-shipping orchestrator ``evaluate_and_run(producer, source)`` for
each — serial execution per CONTEXT Q1.

Failure contract α: a per-producer failure NEVER blocks subsequent
producers nor the caller's state-save. ``evaluate_and_run`` already
wraps each ``Producer.run()`` and returns a ``ProducerResult(status="failed")``
on raise; this caller propagates results without re-raising.

State accumulation: ``state["producer_cost_total"]`` is incremented by
the sum of ``cost_usd`` across all results in this call. It is initialized
to 0.0 on first encounter. The caller persists ``state`` to disk; this
function only mutates the dict.

What stays UPSTREAM in compile.py's per-file loop:

- the decision to call this stage at all (only after the SDK compile +
  knowledge/ write succeeded — failed compiles get no post-pass)
- ``state["total_cost"]`` accumulation (SDK-compile cost, separate concern)
- ``save_state(state)``

T01–T03 land this module parallel to the legacy inline block in
``compile.py:main()``. T04 rewires the call site and deletes the legacy
block.
"""

from __future__ import annotations

import logging
from pathlib import Path

from producers import all_producers
from producers.base import ProducerResult
from producers.orchestrate import evaluate_and_run

from .types import CompileResult

log = logging.getLogger("compile")


async def run_post_passes(
    source_path: Path,
    compile_result: CompileResult,  # noqa: ARG001 — reserved for future producers that key off compile output
    state: dict,
) -> list[ProducerResult]:
    """Run every registered Producer against ``source_path`` serially.

    Returns one ``ProducerResult`` per registered Producer in registration
    order (today: suggestions → curiosity → takes). Skip/fail outcomes are
    represented in the result, never raised. Mutates ``state`` by adding
    each result's ``cost_usd`` into ``state["producer_cost_total"]``.

    ``compile_result`` is accepted for API symmetry with the other
    compile_stages and for future producers that may want to key off the
    compiled article shape; current producers consume the source path only.
    """
    results: list[ProducerResult] = []
    cost_delta = 0.0

    for producer in all_producers():
        result = await evaluate_and_run(producer, source_path)
        results.append(result)
        cost_delta += result.cost_usd

    if cost_delta:
        state["producer_cost_total"] = round(
            state.get("producer_cost_total", 0.0) + cost_delta, 4
        )

    return results
