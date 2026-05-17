---
milestone: M020
status: done
---

# M020 — Roadmap

Single slice, 5 tasks. Per slice-milestone-gate quirk (memory `project_ytstack_slice_gate_quirk`), the slice-plan is written directly without invoking `ytstack:slice-milestone`.

## S01 — Backlinks footer materialization

- [x] T01 — `scripts/core/backlinks.py`: extractor (`build_backlinks_index`) with pipe-alias + anchor + code-fence handling. TDD.
- [x] T02 — `scripts/core/backlinks.py`: writer (`write_backlinks_footer`) with sentinel-managed region + idempotency. TDD.
- [x] T03 — `scripts/core/backlinks.py`: orchestrator (`run_backlinks_pass`) walking KNOWLEDGE_DIR. TDD.
- [x] T04 — `scripts/compile.py`: wire orchestrator into `main()` post-loop. Gate behind `CONFIG.features.materialize_backlinks`.
- [x] T05 — Config knob + migration (same commit, per CLAUDE.md hard rule) + skill-doc update + live-vault probe.

## Verification record

- 21/21 unit tests green in `tests/test_backlinks.py`.
- 24/24 migration tests green in `tests/test_migrate_config_keys.py` after the +1 KEY_ADDITION bump (41 → 42 changes, fixture extended).
- Live-vault dry-run against snapshot of lxw `knowledge/` (1238 articles): full pass 220 ms, 1131 articles received footers, second pass `articles_written=0` (idempotent), operator-prose preserved above sentinel, footer body inspection (`projects/fleet` 181 incoming, `concepts/symptom-vs-root-cause-discipline` 78 incoming) shows clean path-relative wikilinks.
- 10 pre-existing test failures in `test_compile_two_layer_prompt` / `test_dream_sampling` / `test_jamie_extraction_fixture` / `test_lifecycle_*` from the parallel owner-block injection arc (`compile.py:432 _build_owner_block`) — unrelated to M020; the failing tests reference `${owner_block}` placeholder rendering that pre-dates this milestone.
