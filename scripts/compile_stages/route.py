"""Route — the discriminated decision compile_file makes per source (M026).

`decide_route(source, content) → Route` (added in M026-S02) returns one of these
variants *before* any I/O or LLM call. `compile_file` then `match`es on the variant
and dispatches to the matching execution handler. Full design:
`.ytstack/backlog/compile-dispatch-seam.md`.

This module imports `.types` and `.classify`; neither imports `route`, so there is
no cycle — `decide_route` can stay pure while the `Compile` variant carries the
`ClassifyResult` (so the route decision fully describes single-vs-chunked without
re-running classify downstream).
"""

from __future__ import annotations

from dataclasses import dataclass

from .classify import ClassifyResult
from .types import CompileMetadata


@dataclass(frozen=True)
class Skip:
    """No work: empty body / final-only / substrate-skip-list."""

    reason: str


@dataclass(frozen=True)
class IndexOnly:
    """source-and-final file: indexed for discoverability, not distilled.

    `wikilinks` is a tuple so the dataclass stays frozen/hashable-clean. The
    handler that writes the index entry (S03) gets the source `Path` separately.
    """

    title: str
    wikilinks: tuple[str, ...]


@dataclass(frozen=True)
class HealthStub:
    """health-rollup metric stub: recorded deterministically, no agent, $0."""


@dataclass(frozen=True)
class Compile:
    """Needs an LLM call. Carries the upstream dispatch decision + classify result."""

    metadata: CompileMetadata
    classification: ClassifyResult


Route = Skip | IndexOnly | HealthStub | Compile
