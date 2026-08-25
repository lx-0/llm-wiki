---
milestone: M030
project: llm-wiki
size: M
created: 2026-08-25T06:49:07Z
status: planned
total_slices: 3
completed_slices: 0
---

# M030 Roadmap

**Goal:** Every `knowledge/` article and hard fact is readable by the operator's agents anywhere via meinkontext: `wiki publish` maintains a managed wiki there as a one-way, idempotent mirror of the compiled corpus.

**Exit criteria:**
1. `wiki publish` publishes ALL of `knowledge/` per PRODUCER-CONTRACT.md; unchanged rerun = zero writes (content-hash state).
2. Lifecycle proven against live dev server (publish → update → retract-archives → re-publish-restores), mirroring the REFERENCE PRODUCER RUN.
3. Live proof from another machine / claude.ai connector: grounded answer from a published article, Mac asleep.
4. Knobs + migration same commit; publish touches only knowledge/ (read) + .wiki/state/ (write); PROCESS.md + config docs + both infographics in the same arc; suite green.

## Slices

Slice detail lives in per-slice `M030-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [ ] S01 -- Mapping core: offline transform of knowledge/ into contract-shaped payloads (slugs, wikilink normalization, descriptions, content-hash delta, `publish --dry-run`)
- [ ] S02 -- Producer transport: `wiki publish` against meinkontext (JSON-RPC client, wiki bootstrap + start page, write/retract/restore executor, knobs+migration, first full live publish)
- [ ] S03 -- Cadence + proof: compile piggyback, live retraction/restore E2E, reach-anywhere proof with Mac asleep, docs + infographics, closeout

Suggested framing for slicing (not binding): S01 mapping core (slug + wikilink normalization + description sourcing + content-hash state, offline against fixtures) → S02 producer transport (MCP client, create_wiki/write_article/retract/restore against live dev, token bootstrap, knobs + migration) → S03 cadence + docs + live end-to-end proof (piggyback/manual, PROCESS.md, config docs, infographics, closeout).

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update global ROADMAP.md
