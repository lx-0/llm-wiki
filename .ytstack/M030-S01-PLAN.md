---
milestone: M030
slice: S01
project: llm-wiki
created: 2026-08-25T07:01:45Z
status: planned
task_count: 5
completed_tasks: 1
---

# M030-S01 -- Slice Plan

**Goal:** Deterministic, offline transform of the whole `knowledge/` corpus into contract-shaped article payloads — slugs, normalized wikilinks, descriptions, content-hash delta plan — as pure functions with fixture tests; no network.

## Tasks

- [x] T01 -- Corpus walker + slug mapper: enumerate `knowledge/**/*.md` EXCLUDING `knowledge/index.md` (inventory table, replaced by the generated start page — CONTEXT decision), derive flat global kebab-case slugs (bare, no `lw-` prefix). CRITICAL: each slug must be a FIXPOINT of the server's slugification (`slugifySkillName`, skill-validation.ts:151-158: NFKD unicode fold, lowercase, `[^a-z0-9]+`→`-`, hyphen-trim, 120-char cap) — fixpoint property unit-tested, else manifest id and server article id diverge and retraction misses. Detect local collisions deterministically; persist a stable slug↔path manifest in `.wiki/state/publish.json` via `core.state_store`.
- [ ] T02 -- Wikilink normalization reusing the `core.links` resolver: relative-to-file links → `[[target-slug]]`; unresolvable targets and targets outside `knowledge/` degrade to plain text (brackets stripped); fixture tests incl. footer/embed edge cases.
- [ ] T03 -- Description sourcing: per-article summary from the article's `knowledge/index.md` row via the FULL index-row parse (`read_wiki_index` + pipe-sentinel split, utils.py:205-208, shape `['', title, summary, sources, date, '']` — NOT `read_wiki_index_compact`, which strips exactly the summary column), fallback = first body paragraph; enforce non-empty ≤1024 chars; tests for both paths.
- [ ] T04 -- Content-hash delta engine: sha256 over the transformed payload (content + description + start_page flag), diff vs the state manifest → created/changed/deleted sets; idempotency test proves a second run yields an empty plan.
- [ ] T05 -- `wiki publish --dry-run`: CommandSpec entry in the `scripts/cli.py` table printing the publish plan (per-article action + totals, `--json` seam for GUI/agents); golden test on a fixture vault.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
