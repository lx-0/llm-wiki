---
milestone: M007
slice: S03
project: llm-wiki
created: 2026-05-16T15:14:50Z
status: planned
task_count: 6
completed_tasks: 6
---

# M007-S03 -- Slice Plan

**Goal:** Dashboard/MOC/wiki-query filter `final-only` from active surfaces. ≥1 imported/lx/ longform tagged `source-and-final` and verified surfacing end-to-end. archives-flag.md retired. M007 exit criteria all green.

## Tasks

- [x] T01 -- Dashboard pane queries filter `compile_role: final-only` out of active surfaces by default. Touch: `scripts/dashboard/*` (specifically the panes that aggregate concepts/projects/people for active display). Replaces all archives-flag-style thinking — there is no `archived: true` mechanism shipped, only `compile_role: final-only`.
- [x] T02 -- MOC auto-include in `scripts/facts/moc.py` (or wherever MOC generation lives): skips `final-only` from auto-aggregation; **includes** `source-and-final` (longform essays are deliberate writing that should be discoverable). Manual `[[wikilinks]]` in MOC body still resolve regardless.
- [x] T03 -- `wiki query` CLI: default behavior filters `final-only` out of result set; `--include-final-only` flag re-includes. Touch: `scripts/cli.py` (or wherever query subcommand dispatches). Help text updated.
- [x] T04 -- Migration: pick 1-2 imported/lx/ longform docs (candidates: `imported/lx/yesterday-strategy-workdoc.md`, `imported/lx/🌈 Company/Areas/🧬 Mission, Vision, Values/Das Agentische Manifest - Teil 1.md`). Move to `raw/notes/longform/` (creating folder if needed) with `compile_role: source-and-final` frontmatter. Run compile against them. Verify via: (a) Obsidian Search finds them, (b) `knowledge/index.md` lists them by pathname, (c) backlinks built into existing knowledge/ pages, (d) NO separate `knowledge/concepts/yesterday-strategy.md` was created.
- [x] T05 -- `AGENTS.md` + `templates/AGENTS.example.md` document the `compile_role` axis (3 values, default-by-location, lint behavior, when to use which). Delete `.ytstack/backlog/archives-flag.md` (history is preserved in `.ytstack/backlog/lx-vault-merge.md` lineage section + `.ytstack/backlog/compile-role-axis.md` "Coexistence" section + git log). Update `.ytstack/backlog/PRIORITY.md` to remove the strikethrough archives-flag line entirely.
- [x] T06 -- Final smoke against M007-CONTEXT exit criteria: (1) `compile_role` enum recognized + lint-validated → run `wiki lint` clean, (2) compile.py branches 3-way → run `wiki compile --dry-run` on a 3-role fixture, observe correct dispatch, (3) dashboard/MOC/query filter `final-only` → manually verify on lxw vault, (4) ≥1 longform import surfaces → covered by T04 verification, (5) archives-flag retired → grep `.ytstack/` for `archived: true` returns nothing engine-relevant.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution. Issues that surface become entries in `DECISIONS.md` or `KNOWLEDGE.md`.)
