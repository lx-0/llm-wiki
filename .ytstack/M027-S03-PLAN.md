---
milestone: M027
slice: S03
project: llm-wiki
created: 2026-06-07T12:21:47+0200
status: planned
task_count: 4
completed_tasks: 2
---

# M027-S03 -- Slice Plan

**Goal:** The curiosity producer emits `folder-deep-scan` requests that name real
files from the index (verifiable file-exists anchor), and the dispatcher routes
them.

## Tasks

- [x] T01 -- Extend `curiosity/producer.py`: inject the folder-index digest in-context (mirror the numbered `email_folders` listing), emit a `folder-deep-scan` request schema. Replace the `source_quote` gate (no body to quote) with a verifiable file-exists anchor: the named path must be present in the current index. Keep a confidence gate analogous to email's `folder_confidence`.
- [x] T02 -- New prompt `prompts/compile_curiosity_folder.md` (folder-gap detection over the index digest); register it; Ollama-only (producer stays local, split-provider like email).
- [ ] T03 -- `curiosity/cli.py:_dispatch`: add the `folder-deep-scan` branch (skeleton call into the S04 backend; clean "unsupported" removal).
- [ ] T04 -- Tests: producer emits valid file-targeted requests against a fixture index; a request naming a non-indexed file is rejected (anchor works); confidence gate drops low-confidence gaps.

## Done when

All tasks `[x]` and verified. Producer turns an index + a detected gap into a
`folder-deep-scan` request pointing at a real indexed file; invented paths are
dropped.

## Notes

Producer triages off a weak signal (a filename) vs. email's full body -> expect
lower precision; the anchor + confidence gate are the guardrails (M027-CONTEXT
Q7). Depends on S02 (index exists). The backend it dispatches to is S04.
