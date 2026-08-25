---
milestone: M030
slice: S02
task: T04
project: llm-wiki
closed: 2026-08-25T11:45:00Z
verification: passed
---

# M030-S02-T04 -- Summary

## Commits

- `test(publish): producer-lifecycle integration mirroring the REFERENCE PRODUCER RUN (M030-S02-T04)` (committed with this summary)

## Outcome

`tests/test_publish_lifecycle.py` walks the full producer lifecycle through the REAL `ContextMcpClient` + bootstrap + executor against a stateful in-process fake of context-mcp's wiki surface (initialize handshake, list/create wiki, `write_article` with re-slugification via `server_slug` — the S01 fixpoint asserted end-to-end — version bumps, restore-on-write per contract §Lifecycle 5, `delete_object` = archive). Sequence mirrors the upstream run: first publish (4 articles + start page, seq 1, links rewritten to `[[people-alex|Alex]]`), body edit → update seq 2, local delete → retract/archived + manifest cleared, file restore → re-publish restores at seq 3 (upstream's exact `version_seq: 3`), unchanged rerun → zero write calls. Passed first run — no production-code fixes needed.

## Deviations from plan

None.

## Follow-ups

None — S02-T05 (first full LIVE publish of lxw) is the operator-driven step: token + explicit go.

## Verification

Command: `uv run pytest tests/test_publish_lifecycle.py -q` (1 passed) + `uv run pytest -q` (1836 passed, 1 pre-existing skip) -- passed.
