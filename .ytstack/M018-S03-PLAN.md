---
milestone: M018
slice: S03
project: llm-wiki
created: 2026-05-17T12:50:00Z
status: cancelled
cancelled_on: 2026-05-17T13:35:00Z
cancelled_reason: premise-broken — the "write-side logic" doesn't live in Python; the SDK agent owns knowledge/-writes via Write/Edit tools. Extraction would be a re-architecture (strip agent tools + rewrite all substrate prompts to emit a structured manifest + build Python parser/writer). Decision documented in M018-CONTEXT.md; deferred concept in `.ytstack/backlog/commit-article-manifest.md`.
task_count: 3
completed_tasks: 0
---

# M018-S03 — Slice Plan (CANCELLED 2026-05-17)

**Goal:** ~~Pure file I/O `commit_article(article, path)` lives in `scripts/compile_stages/commit.py` and owns frontmatter merge + atomic write to `knowledge/<bucket>/` + index.md append + `compiled_from:` provenance.~~

**Cancellation rationale (subagent-discovered during T01 read):** the legacy `compile.py` does NOT contain the write logic this slice purported to extract. The SDK agent does all `knowledge/` writes inline via `Write(knowledge/**)` + `Edit(knowledge/**)` allowed_tools (legacy branch) or the `can_use_tool` path-scope callback (`d8a0de5`, new branch). Frontmatter merge, `## State` / `## Timeline` discipline (M005), `compiled_from:` provenance, `knowledge/index.md` row updates, and cross-article multi-file updates per compile — all prompt-encoded, all agent-executed. Python only writes for the `source-and-final` index-only branch (compile.py:528-569).

Pursuing this slice would require: (1) strip Write/Edit from compile_source's allowed_tools, (2) rewrite every substrate prompt (compile_main, compile_daily, compile_calendar, compile_health, compile_screenshots, compile_pictures, compile_memories, compile_default) to emit a structured article body or multi-file manifest as final response, (3) build a Python parser + writer that consumes that manifest, (4) preserve the rich agent-side multi-file capability via a `CompileResult.outputs: dict[Path, FileOp]` contract change. That is a re-architecture, not an extraction.

The cheaper honest call: M018 reduces to S02 (✓ shipped) + S04 (post-pass lift). Future re-opening requires a fresh milestone with explicit "manifest emitter + Python writer" scope.

## Tasks

- [ ] T01 -- Identify all write-side logic in `compile.py:main()` (frontmatter merge with operator-edited target file, atomic-replace via tempfile + rename, `knowledge/index.md` append, `compiled_from:` frontmatter list build, two-layer State+Timeline append for entity pages from M005). Extract to `scripts/compile_stages/commit.py:commit_article(result: CompileResult, target_path: Path, metadata: CompileMetadata) → None`.
- [ ] T02 -- Add `tests/test_commit_article.py` with ≥4 cases: (a) new file write lands at `knowledge/concepts/<slug>.md` with correct frontmatter, (b) overwrite preserves operator-edited frontmatter keys (e.g. `dream_priority:`, `pinned:`), (c) two-layer page (M005) appends to `## Timeline` instead of overwriting `## State`, (d) `knowledge/index.md` row gets appended idempotently.
- [ ] T03 -- Wire `compile.py:main()` per-file loop to call `commit_article()` when `CompileResult.status == "ok"`. After this slice: the per-file loop body is `select` (S01 result) + `compile_source` (S02) + `commit_article` (S03) + state-save. Post-passes still inline (S04 lifts). Smoke check: `wiki compile <one-source>` on lxw lands a knowledge/ article + index.md gets the row.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`. `commit_article()` independently importable, ≥4 unit tests, lxw smoke run lands article + index row. The per-file loop body in `compile.py:main()` is materially shorter than at HEAD.

## Notes

Frontmatter merge is the highest-risk subroutine — operator-edited keys must survive overwrites (M005 dashboard pin, M017 dream-priority, M013 domain). Test (b) is the critical regression guard. State-save logic stays in `main()` until S04 (it's per-file-loop bookkeeping, not commit-stage logic). After S03 lands, the per-file loop body should be <40 LOC per CONTEXT exit-criterion #1 — even before the post-pass lift.
