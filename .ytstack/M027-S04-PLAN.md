---
milestone: M027
slice: S04
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 5
completed_tasks: 0
---

# M027-S04 -- Slice Plan

**Goal:** The folder-backend reads named local files in-place and persists the
distilled answer only -- no raw body ever enters the vault (the P2 contract) --
behind a swappable provider seam.

## Tasks

- [ ] T01 -- `curiosity/backends/folder.py`: read the request's named local files in-place and transiently (path-scoped to those exact paths via `make_path_scope_hook`, explicit tool allowlist), run an agentic pass to answer the request topic. Put the read+answer behind a **provider seam** (config-selected): Claude SDK now; a local LLM/agent must be able to replace it later with the same request/answer contract (DECISIONS 2026-06-07). Not a silent fallback -- an explicit configured provider.
- [ ] T02 -- Persist the result **answer-only** per the S01 answer-landing contract; assert in a test that no raw file body is written anywhere under the vault (P2). Tag the answer with the source file's mtime.
- [ ] T03 -- Failure/quarantine path (file gone between index and read, read error) -- mark the request failed without aborting the batch (email's `MailboxReadError`/watermark-on-failure is the template); staleness carried so a later source change can invalidate.
- [ ] T04 -- e2e test on a real local trove: gap -> `folder-deep-scan` -> in-place read -> answer artifact; assert the answer captures the fact AND no raw body landed in the vault.
- [ ] T05 -- Informed-consent walk card: extend `curiosity/cli.py:_walk`'s request card for `folder-deep-scan` to state which file(s) will be loaded and which backend/provider they'll be sent to ("file X -> <provider> to answer Y"), so the operator's accept is informed. This is the content/cloud gate UX (DECISIONS 2026-06-07).

## Done when

All tasks `[x]` and verified. A local-folder curiosity request produces a
distilled answer with zero raw-body persistence, verified end-to-end.

## Notes

This is the milestone's novel contract. CloudStorage/NAS reads hit the TCC wall
and need the out-of-sandbox reader (S06 T02) -- this slice proves the contract on
plain-local paths first. Depends on S01 (answer-landing + sanitization) and S03
(request shape).
