"""Shared types for the compile_stages package.

CompileResult mirrors ProducerResult's shape (status: ok/skipped/failed,
reason, cost) so end-of-run aggregation reads both seam outputs uniformly.
CompileMetadata carries the input-side decisions that compile_source needs
but didn't make itself (the upstream main() loop decides compile_role,
substrate_type → model + max_turns dispatch, before calling compile_source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


CompileStatus = Literal["ok", "skipped", "failed"]
CompileRole = Literal["source-only", "source-and-final", "final-only"]


@dataclass(frozen=True)
class CompileResult:
    """What `compile_source()` returns. Pure return value — no file I/O.

    Status semantics:
    - ``ok``     — SDK call returned a final article body. `article` holds it,
                   `cost_usd` / tokens populated, `frontmatter_extra` carries
                   any merged YAML the function decided.
    - ``skipped`` — pre-flight gate or kind-unknown skip-and-flag fired before
                   or instead of a usable SDK result. `skip_reason` names which.
                   Caller proceeds to next file; state-save still happens.
    - ``failed`` — SDK call raised or returned an unrecoverable failure class
                   (rate_limit, cli_crash, auth, model, network). `failure_kind`
                   names which. Caller decides abort vs. continue per its
                   consecutive-failure budget.
    """

    status: CompileStatus
    article: str | None = None
    frontmatter_extra: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    skip_reason: str | None = None
    failure_kind: str | None = None
    failure_detail: str | None = None
    """Free-form description from `FailureClass.detail` — surfaced in
    main()'s fatal-abort log line. Without this the operator sees
    `kind=X | (see logs)` and must hunt the stderr archive for the
    actual cause."""


@dataclass(frozen=True)
class CompileMetadata:
    """Input-side decisions main() makes before calling compile_source.

    The upstream loop reads frontmatter, infers compile_role, dispatches on
    substrate_type to pick model + max_turns, then hands compile_source a
    fully-prepared context. compile_source does NOT re-infer these.
    """

    source_path: Path
    compile_role: CompileRole
    model_id: str
    max_turns: int
    substrate_type: str | None
    substrate_prompt: str = "compile_main"
    # Memory-substrate pre-pass results (compile_stages.memory). Resolved
    # by `compile.py` before SDK call so the prompt stays mechanical:
    # `project_slug` populates the prompt's `${project_slug}` var,
    # `project_page_rel` populates `${project_page}` (vault-relative path
    # the agent can Read directly). Both None for non-memory substrates
    # OR memory substrates whose project page couldn't be resolved (those
    # short-circuit to `_skipped: memory_no_project_page` upstream and
    # never reach compile_source).
    project_slug: str | None = None
    project_page_rel: str | None = None


@dataclass(frozen=True)
class CompileOutcome:
    """What `compile_file()` returns — one typed result per source (M026).

    Replaces the legacy magic-key dict (`{"_skipped": …}` / `{"_failure": …}` /
    usage-dict). Mirrors `CompileResult` / `ProducerResult` so end-of-run
    aggregation reads uniformly.

    `failure_kind`/`failure_detail` are strings (not a `FailureClass` object) —
    same choice as `CompileResult`, keeps this module free of a
    `core.sdk_helpers` import. `main()` reconstructs `FailureClass` from them when
    it needs the consecutive-failure abort heuristic.

    `ingest_hash` replaces the `_STATE_MUTATING_SKIPS` registry: execution
    handlers no longer self-persist state; `main()` is the single state-save site
    and persists `state["ingested"][rel]=hash` iff this is True.
    """

    status: Literal["compiled", "skipped", "failed"]
    skip_reason: str | None = None
    failure_kind: str | None = None
    failure_detail: str | None = None
    ingest_hash: bool = False
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    article: str | None = None
