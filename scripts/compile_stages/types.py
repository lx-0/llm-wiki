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
