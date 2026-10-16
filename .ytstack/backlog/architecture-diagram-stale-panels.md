# `docs/architecture.excalidraw`: two panels predate later milestones

**Status:** open. Recorded 2026-10-16 (M034-S06-T06). M034 left the diagrams out (arc §8);
its own rule was to change them only where a box named an M034-moved component, and none
did.

**What is stale (read from the file, not rendered):**
- **The piggyback schedule panel** lists `scan-email --incremental`, `scan-screenshots` and
  `scan-youtube`, names from before the collector migration. Today the collector piggybacks
  are named by collector (`email`, `screenshots`, …). youtube is `piggyback_default=False`, so
  it is never auto-spawned. The panel lacks voice, pictures, capture and wispr. It also lacks
  the built-in tasks `review_wiki`, `daily_digest_yesterday`, `dream_cycle`, `study_run_due`,
  `analyst_pass2`, `concept_reconcile` and `health_trends`. Source of truth:
  `core/piggybacks.py:_BUILTIN_PIGGYBACK_TASKS` plus `wiki collect --list`'s piggyback
  column.
- **The facts box** says reconcile is "cost-capped". USD caps were replaced by structural
  gates on 2026-05-23 (`concept_reconcile_max_files_per_fact` / `_max_facts_per_run`,
  DECISIONS 2026-05-23).

**How:** an edit to `docs/*.excalidraw` passes CLAUDE.md's three render gates (bbox overlap,
glyph width, zoom-crop review). A steady-state portrait: no milestone tags.
