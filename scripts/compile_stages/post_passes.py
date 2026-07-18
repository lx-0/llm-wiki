"""Post-pass stage of the compile pipeline (M018-S04).

``run_post_passes(source_path) → list[ProducerResult]`` owns the per-file
post-pass loop that Phase 1 (commit ``e730d26``) wired inline into
``compile.py:main()``. It iterates ``ProducerRegistry.all_producers()`` in
registration order (suggestions → curiosity → takes) and calls the
already-shipping orchestrator ``evaluate_and_run(producer, source)`` for
each — serial execution per CONTEXT Q1.

Failure contract α: a per-producer failure NEVER blocks subsequent
producers nor the caller's state-save. ``evaluate_and_run`` already
wraps each ``Producer.run()`` and returns a ``ProducerResult(status="failed")``
on raise; this caller propagates results without re-raising.

Producers consume the source path only — per-producer LLM usage is recorded
centrally by the token ledger (``core/usage.py``), so no compile-result or
state is threaded through (the old dollar-shaped ``producer_cost_total``
accumulator was removed, DECISIONS 2026-05-23).

What stays UPSTREAM in compile.py's per-file loop:

- the decision to call this stage at all (only after the SDK compile +
  knowledge/ write succeeded — failed compiles get no post-pass)
- ``state["total_cost"]`` accumulation (SDK-compile cost, separate concern)
- ``save_state(state)``
"""

from __future__ import annotations

import logging
from pathlib import Path

from producers import all_producers
from producers.base import ProducerResult
from producers.orchestrate import evaluate_and_run

log = logging.getLogger("compile")


async def run_post_passes(source_path: Path) -> list[ProducerResult]:
    """Run every registered Producer against ``source_path`` serially.

    Returns one ``ProducerResult`` per registered Producer in registration
    order (today: suggestions → curiosity → takes). Skip/fail outcomes are
    represented in the result, never raised. Producers consume the source path
    only; per-producer usage is recorded centrally via ``core/usage.py``.
    """
    results: list[ProducerResult] = []
    for producer in all_producers():
        results.append(await evaluate_and_run(producer, source_path))

    if results:
        _log_summary(results)

    return results


def _log_summary(results: list[ProducerResult]) -> None:
    """One-line operator-facing summary of which producers ran for this source.

    Without this line a compile with all-skipped producers looks like
    post-passes never ran. Format mirrors the compile per-file ✓ line
    so it visually parents under the source it relates to.
    """
    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    parts = []
    for r in results:
        marker = {"ok": "✓", "skipped": "·", "failed": "✗"}[r.status]
        parts.append(f"{marker}{r.producer}")
    breakdown = " ".join(parts)
    log.info(
        "  post-pass: %d ok · %d skipped · %d failed — %s",
        ok, skipped, failed, breakdown,
    )
