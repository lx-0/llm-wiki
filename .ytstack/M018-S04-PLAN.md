---
milestone: M018
slice: S04
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: planned
task_count: 3
completed_tasks: 0
---

# M018-S04 — Slice Plan

**Goal:** Pure file I/O `commit_article(article, path)` lives in `scripts/compile_stages/commit.py` and owns frontmatter merge + atomic write to `knowledge/<bucket>/` + index.md append + `compiled_from:` provenance.

## Tasks

- [ ] T01 -- Identify all write-side logic in `compile.py:main()` (frontmatter merge with operator-edited target file, atomic-replace via tempfile + rename, `knowledge/index.md` append, `compiled_from:` frontmatter list build, two-layer State+Timeline append for entity pages from M005). Extract to `scripts/compile_stages/commit.py:commit_article(result: CompileResult, target_path: Path, metadata: CompileMetadata) → None`.
- [ ] T02 -- Add `tests/test_commit_article.py` with ≥4 cases: (a) new file write lands at `knowledge/concepts/<slug>.md` with correct frontmatter, (b) overwrite preserves operator-edited frontmatter keys (e.g. `dream_priority:`, `pinned:`), (c) two-layer page (M005) appends to `## Timeline` instead of overwriting `## State`, (d) `knowledge/index.md` row gets appended idempotently.
- [ ] T03 -- Wire `compile.py:main()` per-file loop to call `commit_article()` when `CompileResult.status == "ok"`. After this slice: the per-file loop body is `select` (S02 result) + `compile_source` (S03) + `commit_article` (S04) + state-save. Post-passes still inline (S05 lifts). Run S01 regression vault — must stay green.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `commit_article()` independently importable, ≥4 unit tests, regression vault byte-identical. The per-file loop body in `compile.py:main()` is materially shorter than at HEAD.

## Notes

Frontmatter merge is the highest-risk subroutine — operator-edited keys must survive overwrites (M005 dashboard pin, M017 dream-priority, M013 domain). Test (b) is the critical regression guard. State-save logic stays in `main()` until S05 (it's per-file-loop bookkeeping, not commit-stage logic). After S04 lands, the per-file loop body should be <40 LOC per CONTEXT exit-criterion #1 — even before the post-pass lift.
