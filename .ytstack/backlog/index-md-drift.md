# Backlog: knowledge/index.md drift — 561 missing, 362 duplicate rows

Found by the 2026-08-25 full-state audit. The catalog no longer reflects the
corpus: 1844 rows / 1482 unique vs 2022 real articles → 561 articles unlisted
(concepts 516, projects 14, people 11, MOCs 9, facts 8); 362 duplicate rows
(people/sidney-wach 18×, felix-weichert 17×, chris-von-rhein 16×, zuhause 12×);
42 dangling rows incl. junk targets (`[[! -o monitor]]`, `[[foo]]`).

## Why it matters

- The compact index seeds query/compile prompts — 561 articles are invisible to
  every LLM pass that relies on it.
- publish sources descriptions from index rows — 561 articles fall back to
  first-paragraph descriptions in the mirror.
- Duplicate rows correlate with the most-compiled entities → suspect: the
  compile index-writer appends instead of upserting when the row already exists
  (or title variants defeat the match).

## Fix shape

1. Root-cause the writer (upsert-by-target, not by title string).
2. One-shot reconciliation command (`wiki index rebuild`?): dedupe rows, append
   missing articles with generated summaries (deterministic from body first
   paragraph — NO LLM needed for backfill), drop dangling junk rows.
3. Lint check: index row count vs corpus count drift gate.
