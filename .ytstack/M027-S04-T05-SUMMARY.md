---
milestone: M027
slice: S04
task: T05
project: llm-wiki
closed: 2026-06-10T23:05:00+0200
verification: passed
---

# M027-S04-T05 -- Summary

## Commits

- `5f9e04d` -- feat(M027-S04-T05): informed-consent walk card — exit criterion #2
- `510409e` -- plan(M027-S04-T05): informed-consent walk card — closes exit criterion #2

## Outcome

The walk card is the content/cloud gate UX now (**milestone exit
criterion #2 closed**). `_print_request_card` branches on
`type: folder-deep-scan` and renders: `File: <root_id>/<file_path>` +
confidence, the resolved absolute path (via the backend's `_resolve`)
with a live `exists` / `MISSING — stale index?` marker — the operator
sees staleness BEFORE approving — and the consent line:

```
⚠ Accept will LOAD this file and send its content to 'claude-sdk'
  to answer: "<topic>"
```

`<provider>` comes from `CONFIG.models.folder_scan_provider`, so a
future local provider honestly renders as local. "Why this file:"
rationale block kept. Email cards render unchanged (regression-pinned,
no consent line); `_walk`'s accept→dispatch flow untouched.

## Deviations from plan

None — folder body extracted into `_print_folder_card_body` (the email
path stays byte-identical inline).

## Follow-ups

- **S04 COMPLETE (5/5)** → `/ytstack:reassess-roadmap` at the slice
  boundary. S05 (compile-fold) was pre-marked "likely lighter"
  (compile-primary per the S01 reassessment) — re-scope there.
- lxw note: engine on origin via auto-push; `wiki update` already pulled
  the provider knob earlier — the full S04 backend goes live on the
  operator's NEXT `wiki update`. The producer (S03) is live and may
  already be queueing pending requests for the walk.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py -q` then
`uv run pytest -q` -- passed. Full suite **1262 passed, 1 skipped**
(1259 → 1262; skip = gated live e2e).
