---
milestone: M027
project: llm-wiki
size: L
created: 2026-06-07T12:21:47+0200
status: planned
total_slices: 6
completed_slices: 3
---

# M027 Roadmap

**Goal:** The wiki learns from the operator's watched local + NAS folders: a
body-blind index feeds curiosity requests that read selected files in-place
(answer-only, no raw copy), and the dream-cycle folds the derived facts into
`knowledge/` over time -- so "what do you know about my X" draws on real file
troves, not just the narrative layer.

**Exit criteria:**
1. Metadata index unmasked (filenames/structure/size/mtime); content never in the index.
2. Human-approval walk is the content/cloud gate -- content loaded + processed only after per-request accept; walk card shows informed-consent text.
3. Answer-landing contract pinned + implemented (technical decision, not a PII gate).
4. `personal.watched_folders` (local + smb) via config + migration; body-blind index for >=1 local and >=1 NAS root.
5. Producer `folder-deep-scan` (file-exists anchor) + `backends/folder.py` read-in-place, answer-only, verified on a real trove.
6. Dream/compile folds >=1 folder-derived fact into `knowledge/` live on lxw; trove-topic query returns a folder-sourced fact.
7. Staleness invalidation + failure/quarantine path covered by tests.

## Slices

Slice detail lives in per-slice `M027-S##-PLAN.md` files, created by
`ytstack:slice-milestone`. (The earlier "front-load the 3 gates" rule is
superseded -- see DECISIONS 2026-06-07; the human-approval walk is the content
gate, so the index can be built freely and S01 is slimmed.)

- [x] S01 -- Config + answer-landing contract: `watched_folders` schema + decide where the backend's distilled answer persists
- [x] S02 -- Body-blind folder-index collector for local roots -> unmasked delta-aware `raw/index/<root>.md` (`wiki index`; "sanitized" wording superseded by DECISIONS 2026-06-07)
- [x] S03 -- Curiosity producer emits `folder-deep-scan` (file-exists anchor) + dispatch branch
- [ ] S04 -- Folder-backend: read named local files in-place, persist answer-only (no raw body)
- [ ] S05 -- Dream/compile fold folder-derived facts into `knowledge/` with sensitivity applied
- [ ] S06 -- NAS (SMB) + out-of-sandbox reader + periodic scheduler

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap`
checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` -> `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` -> `status: done` and update global ROADMAP.md
