"""compile_stages — pure-ish stage functions extracted from compile.py.

M018 refactor of the compile pipeline. compile.py's per-file loop calls
these stages in order:

  1. (selection stays in compile.py:select_files() — already factored)
  2. compile_source(content, metadata) → CompileResult         (S02)
  3. run_post_passes(source) → list                             (S04)

compile_source is the LLM-call boundary, run_post_passes the
ProducerRegistry orchestrator. There is no write stage: the compile agent
writes into knowledge/ itself, path-scoped by the PreToolUse hook
(`core/sdk_scope.py`) — the planned `commit_article` stage (S03) was
cancelled (8bd6cd9) because those writes are agent-side, and taking them
away is `backlog/compile-agent-no-filesystem-write.md`.

See `.ytstack/M018-CONTEXT.md` and `.ytstack/backlog/producer-seam.md`.
"""

from __future__ import annotations

from .route import Compile, HealthStub, IndexOnly, Route, Skip
from .types import CompileMetadata, CompileOutcome, CompileResult

__all__ = [
    "Compile",
    "CompileMetadata",
    "CompileOutcome",
    "CompileResult",
    "HealthStub",
    "IndexOnly",
    "Route",
    "Skip",
]
