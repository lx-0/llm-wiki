---
milestone: M027
slice: S02
task: T03
project: llm-wiki
closed: 2026-06-10T16:05:00+0200
verification: passed
---

# M027-S02-T03 -- Summary

## Commits

- `7d03314` -- feat(M027-S02-T03): folder-index delta-skip + compile-skip wiring
- `b696b23` -- plan(M027-S02-T03): delta-awareness + folder-index compile-skip wiring

## Outcome

**(A) Delta-awareness** in `collectors/folder_index.py`:
`index_signature()` hashes the walked tree (sha256 over sorted
`(rel_path, is_dir, size, mtime)` tuples — `generated_at`/counts excluded,
honoring the T02 carry that per-walk frontmatter must not defeat the diff).
`sync_root()` walks a root, compares the signature against side-state
`state/folder-index.json` ({root_id: {signature, last_indexed_at}}), and
skips the write on unchanged trees (`SyncResult(written=False,
reason="unchanged")`); it re-writes when the signature changed, on
`force=True`, or when the operator deleted the digest file (existence
check guards the skip). Missing/corrupt state fails soft into a full
rebuild.

**(B) Compile-skip wiring:** `folder-index` is now in
`compile_skip_substrate_types` — `config.py` default, `config.example.yaml`,
migration `KEY_ADDITIONS` default AND `LIST_ADDITIONS` append, all in the
same commit (config-migration hard rule). The route layer Skips any
`type: folder-index` source and the 0.1.7 Skip route hash-records it
(`ingest_hash=True`), so digests never re-list until their body changes.
Carry-constraint pinned by regression test in `test_decide_route.py`:
`raw/notes/folder/` answer files still route to Compile.

## Deviations from plan

- The plan's "possibly touch migration round-trip fixtures" materialized:
  2 fixtures synced (round-trip stays 84 changes — greenfield KEY_ADDITIONS
  injects both list values in one change; value-assert updated to
  `["email-delta", "folder-index"]`; fully-current fixture extended).
- None otherwise — plan held.

## Follow-ups

- **Coverage gap found+fixed en route:** `migrate_list_additions` (the
  append path live vaults take on `wiki update`) had ZERO test coverage
  since 2026-05-16 — now covered incl. idempotence + operator-custom
  preservation (`test_migrate_list_additions_appends_to_existing_operator_list`).
- ⚠️ Unit-verified only; lxw picks up the list-append after `wiki update`.
- T04 (last slice task): CLI `wiki index` verb + registry wiring + lift
  `max_depth`/`recent_n`/`max_tree_entries` to config knobs (+ migration,
  same commit). `templates/` has no skip-list references — no resync needed.

## Verification

Command: `uv run pytest tests/test_folder_index_collector.py -q` then
`uv run pytest -q` -- passed. Full suite **1225 passed, 0 failed**
(1219 → 1225: 4 delta + 1 routing + 1 migration-append test).
