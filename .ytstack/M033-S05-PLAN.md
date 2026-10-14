---
milestone: M033
slice: S05
project: llm-wiki
created: 2026-10-14T18:50:00+02:00
status: planned
task_count: 6
completed_tasks: 0
---

# M033-S05 -- Slice Plan

**Goal:** A type checker is a gate on `core/`, the schema-2 `--json` contracts are typed once and validated by both suites, and the milestone closes with its docs, CHANGELOG 0.7.0, the full backlog fan-out and the roadmap reassessed.

## Tasks

- [ ] T01 -- Type-checker probe and decision: `uv add --dev` pyright and ty, run both in `basic` mode on `scripts/core/` and on all of `scripts/`, record findings and wall time, pick one (CONTEXT open question 1), remove the other, write the DECISIONS entry; config in `pyproject.toml`.
- [ ] T02 -- `scripts/core/` green under the chosen checker: real annotations instead of `Any` where the fix is local, `TypedDict` / dataclasses for the dict-shaped payloads the desktop reads, `# type: ignore[code]` with reason only where a dependency is untyped; the checker added to pre-commit and `ci.yml` scoped to `core/`; the count for the rest of `scripts/` recorded in `KNOWLEDGE.md`.
- [ ] T03 -- Contract typed once: the `menu --json` / `doctor --json` payloads defined as dataclasses in `core/actions.py` (they largely are), a JSON Schema generated from them into `docs/contracts/actions.schema.json` by a committed script, and a pytest that validates the oracle's golden payloads against it (`jsonschema` is already in the lock — verified).
- [ ] T04 -- Desktop side of the contract: `desktop/` validates its fixtures (`scripts/shots/fixtures.cjs`, `src/vault/*.test.ts`) against the same schema in vitest (`ajv` dev dependency), and `src/lib/actions.ts` either imports generated types (`json-schema-to-typescript`) or keeps its hand-written types with a test that fails when the schema gains a field — decided by the schema's size (CONTEXT open question 2).
- [ ] T05 -- Closeout docs + release: `docs/engine-layout.md` (seams, gates — the file-by-file tree and `AGENTS.md`'s directory map were reconciled in S02-T05: re-verify against `ls` after S03/S04, do not rewrite), `README.md` dev section, `CHANGELOG.md` `[0.7.0]` + `pyproject.toml` + `uv lock`, DECISIONS (milestone entry) and KNOWLEDGE (toolchain lessons), `docs/architecture.excalidraw` only if a box changed (CLAUDE.md infographic rule).
- [ ] T06 -- Milestone close: the full backlog fan-out against the code (DECISIONS 2026-08-27 method — every SHIPPED verdict refuted first), `PRIORITY.md` re-cut, then `ytstack:reassess-roadmap` (last slice) and the M034 pitch re-read against what M033 actually left.

## Done when

All tasks marked `[x]` and verified via `ytstack:summarize-task`.

## Notes

- Operator vaults pull `wiki update` after this slice: T05's release note must say what changed for them (entry points, gates) and what did not (no config knob, no migration).
