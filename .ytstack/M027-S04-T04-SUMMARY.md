---
milestone: M027
slice: S04
task: T04
project: llm-wiki
closed: 2026-06-10T22:35:00+0200
verification: passed
---

# M027-S04-T04 -- Summary

## Commits

- `ae60994` -- test(M027-S04-T04): live e2e — first real SDK read of the folder path PASSED
- `1bf7d05` -- plan(M027-S04-T04): env-gated live e2e — first real SDK read of the provider path

## Outcome

The full folder-deep-scan path is **live-verified end-to-end** — the
REGEL-#1 boundary for the mocked T01–T03 chain is cleared.
`tests/test_folder_scan_live.py` (gated `LLM_WIKI_LIVE_E2E=1`; the normal
suite skips it, staying $0/deterministic) plants a real trove file with a
target fact + raw-body marker, writes a pending request, and runs
`cli._dispatch` with the REAL ClaudeSdkProvider. Observed live (13.7s,
one `compile_model` call, first-run pass — no prompt tuning needed):

- Answer artifact: direct answer **`KX-4711-2024`** with line-level
  source attribution ("Zeile 3 von mobilfunk-vertrag-notizen.md"),
  side-facts flagged as context — exactly the prompt's contract.
- **P2 held live:** the raw-body marker string persisted nowhere under
  the vault root.
- Provenance exact: `as_of_mtime` matches the file's stat,
  `provider: claude-sdk`, request flipped `done` with `output`.

## Deviations from plan

None — single gated test file; the planned prompt-tuning loop was not
needed (first-run pass).

## Follow-ups

- T05 (last S04 task): informed-consent walk card in `_walk` —
  the content/cloud-gate UX. Note: today the e2e dispatched WITHOUT a
  walk approval because tests construct the request directly; the
  operator-facing path must always go through the card.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `LLM_WIKI_LIVE_E2E=1 uv run pytest
tests/test_folder_scan_live.py -q` (live, passed) + `uv run pytest -q`
-- passed. Full suite **1259 passed, 1 skipped** (the gated live test).
