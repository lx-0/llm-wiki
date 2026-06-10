---
milestone: M027
slice: S03
task: T01
project: llm-wiki
closed: 2026-06-10T18:20:00+0200
verification: passed
---

# M027-S03-T01 -- Summary

## Commits

- `8db9909` -- feat(M027-S03-T01): folder-curiosity producer + digest full-paths/timestamps
- `c2cbcf2` -- plan(M027-S03-T01): folder-curiosity producer — digest in-context + file-exists anchor

## Outcome

`curiosity/producer.py` gained `maybe_generate_folder_requests(source)` —
the folder sibling of the email pass (Ollama-only, split-provider, same
drop-counter discipline and error handling). It loads all digests from
`raw/index/` and injects them in-context with a consumer-side budget trim
(over `curiosity_max_prompt_chars` minus excerpt/overhead, Tree
file-lines are dropped while dir skeleton + Recent survive — logged, no
silent cap; DECISIONS 2026-06-10). Schema: gaps of `{topic, root_id
(enum), file_path, file_confidence 1-5, rationale}`. The
anti-hallucination gate is the **file-exists anchor**: `file_path` must
be present in the digest the model saw (`_indexed_paths` extracts all
backticked rel_paths); invented paths drop as `file_not_indexed`.
Confidence reuses `curiosity_folder_confidence_min`; slug dedup +
rejected-tombstones reused. Requests land as
`raw/requests/request-<slug>-<date>.json` with `type: folder-deep-scan`,
`status: pending`, root_id/file_path/file_confidence/topic/rationale/
source/created.

Digest prereq amendment in `collectors/folder_index.py`: Tree lines now
carry FULL rel_paths (quotable anchor + grep-able), and every file line
(Recent + Tree, unified `_file_line` helper) carries
`· size · created YYYY-MM-DD · modified YYYY-MM-DD`.

## Deviations from plan

- **Mid-task operator addition:** created/updated timestamps per file
  line ("nur filesize ist zu wenig"). `IndexEntry.ctime` via
  `st_birthtime` (None on platforms without; `created` then omitted);
  NOT part of the delta signature. Folded into the same render
  amendment + tests.
- lxw re-rolled beyond plan scope (wiki update + `wiki index --force`):
  both live digests now in the full-path + timestamps format —
  live-verified (Sparkasse PDF line shows created/modified).

## Follow-ups

- **`created` honesty caveat:** st_birthtime is LOCAL birthtime — sync
  tools reset it (a Hetzner invoice shows created=sync-date, not
  document date). Fine as triage signal; never present it as document
  date. Consider for S04's answer provenance.
- T02 next: `prompts/compile_curiosity_folder.md` — render() is live
  with `source_path`/`source_content`/`folder_digests`/`timestamp`
  kwargs; tests stub it, so the template is the only missing piece for
  a real pass.
- T03 carries (from plan): `producers/folder_curiosity.py` registration
  (+ `producers/__init__.py` import) AND the `_dispatch` branch.
- None for DECISIONS/KNOWLEDGE beyond what's already locked.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py
tests/test_folder_index_collector.py -q` then `uv run pytest -q` --
passed. Full suite **1237 passed, 0 failed** (1231 → 1237).
