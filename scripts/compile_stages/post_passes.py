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

State: ``run_post_passes`` does NOT mutate ``state`` — per-producer LLM
usage is recorded centrally by the token ledger (``core/usage.py``), so the
old dollar-shaped ``producer_cost_total`` accumulator was removed (DECISIONS
2026-05-23). ``state`` is still accepted for API symmetry and future use.

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
    state: dict,  # noqa: ARG001 — reserved; usage now recorded centrally via core/usage.py
) -> list[ProducerResult]:
    """Run every registered Producer against ``source_path`` serially.

    Returns one ``ProducerResult`` per registered Producer in registration
    order (today: suggestions → curiosity → takes). Skip/fail outcomes are
    represented in the result, never raised. Does not mutate ``state`` (token
    usage is recorded centrally via ``core/usage.py``).

    ``compile_result`` is accepted for API symmetry with the other
    compile_stages and for future producers that may want to key off the
    compiled article shape; current producers consume the source path only.
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
