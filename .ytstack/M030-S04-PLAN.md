---
milestone: M030
slice: S04
project: llm-wiki
created: 2026-08-25T11:40:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M030-S04 -- Slice Plan

**Goal:** ALLES vault-wide into ONE wiki (operator decisions 2026-08-25: whole vault, and "Substrat und Destillat gehören zusammen"): every markdown file under knowledge/, raw/, daily/, reports/, workspace/ publishes into the single managed wiki `llm-wiki`; the 2022 already-live articles keep their slugs (zero retraction on rollout).

## Tasks

- [ ] T01 -- Multi-root corpus core: `map_slugs(vault, roots, previous)` (knowledge keeps the iter_articles walker incl. index.md exclusion; other roots walk `**/*.md` excluding hidden), rel keys become VAULT-relative; manifest layout migration (v1 knowledge-relative → v2 vault-relative, auto on load, one-shot, locked) with a no-phantom-retraction test.
- [ ] T02 -- Pipeline rebase + knob: describe/render/delta/cli/bootstrap on vault-relative rels; `publish.roots` (list, default `["knowledge"]`) in schema + example + migration + docs regen; dry-run prints per-root totals AND the count of skipped non-markdown files (no silent caps); start page shows per-corpus counts.
- [ ] T03 -- Decisions + docs: DECISIONS.md entries (ALLES vault-wide overrides the raw-never-leaves posture for the operator's own org; ONE-wiki decision; markdown-only boundary with assets as open upstream ask); OFFICE-HOURS artifact + M030-CONTEXT updated.
- [ ] T04 -- Live rollout on lxw: `wiki update` → set `publish.roots` → dry-run review MUST show ~4551 create / 0 retract (manifest-migration live proof — abort on any retraction) → `wiki publish` → get_status echo (~6570 knowledge) → idempotent rerun.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

(Add observations during slice execution.)
