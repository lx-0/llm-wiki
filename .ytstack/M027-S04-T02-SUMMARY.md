---
milestone: M027
slice: S04
task: T02
project: llm-wiki
closed: 2026-06-10T21:30:00+0200
verification: passed
---

# M027-S04-T02 -- Summary

## Commits

- `f4051fd` -- feat(M027-S04-T02): answer-only persistence + request flip — the P2 contract
- `1fce04f` -- docs(M027-S04): close T01 (Q9 seam shipped) + plan T02 (answer-only persistence)

## Outcome

`backends/folder.py`'s real run is live end-to-end (provider mocked at
the seam): resolve → exists-check → `get_provider().answer(...)` →
dispatch on the `ScanAnswer`. Success persists
`raw/notes/folder/answer-<slug>.md` (slug lifted from the request
filename, email-backend precedent) with provenance frontmatter —
`type: note`, `kind: folder-deep-scan`, topic, root_id, JSON-quoted
file_path, **`as_of_mtime`** (the staleness tag), `provider`, origin,
request_source/created, processed_at — and the provider's distilled
answer verbatim as body; the artifact is a normal compile SOURCE (S01
option (a)). The request flips to `status: done` with `output` +
`as_of_mtime` (email symmetry, incl. using "done" not "processed").
NOT-ANSWERED sentinel and provider errors persist NOTHING and leave the
request byte-untouched; a missing file (stale index) fails soft before
the provider is even constructed. **P2 is test-pinned:** a vault-wide
file sweep asserts the trove's raw-body marker string persists nowhere.

## Deviations from plan

- Request flip uses `status: "done"` (engine convention from the email
  backend) instead of the plan's "processed" — symmetry won.
- The T03-skeleton test asserting "not implemented (S04)" was rewritten
  to the new stale-index path (same no-mutation guarantee, new reason).

## Follow-ups

- T03 next: failure/quarantine — turn today's raw `success=False` returns
  (provider error / not_answered / file missing) into explicit request
  states that don't re-dispatch forever (email `_mark_error` is the
  template) + staleness invalidation via the persisted `as_of_mtime`.
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py -q` then
`uv run pytest -q` -- passed. Full suite **1256 passed, 0 failed**
(1252 → 1256).
