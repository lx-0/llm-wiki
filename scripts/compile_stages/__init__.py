"""compile_stages — pure-ish stage functions extracted from compile.py.

M018 refactor of the compile pipeline. compile.py's per-file loop calls
these stages in order:

  1. (selection stays in compile.py:select_files() — already factored)
  2. compile_source(content, metadata) → CompileResult         (S02)
  3. commit_article(result, target_path, metadata) → None      (S03)
  4. run_post_passes(source, compile_result) → list             (S04)

Each stage owns one concern: compile_source is the LLM-call boundary,
commit_article is the knowledge/ write boundary, run_post_passes is the
ProducerRegistry orchestrator. compile.py:main() shrinks to a thin
orchestrator over these.

See `.ytstack/M018-CONTEXT.md` and `.ytstack/backlog/producer-seam.md`.
"""

from __future__ import annotations

from .types import CompileMetadata, CompileResult

__all__ = ["CompileMetadata", "CompileResult"]
