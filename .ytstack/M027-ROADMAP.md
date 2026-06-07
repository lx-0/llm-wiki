---
milestone: M027
project: llm-wiki
size: L
created: 2026-06-07T12:21:47+0200
status: planned
total_slices: 4
completed_slices: 0
---

# M027 Roadmap

**Goal:** The wiki learns from the operator's watched local + NAS folders: a
body-blind index feeds curiosity requests that read selected files in-place
(answer-only, no raw copy), and the dream-cycle folds the derived facts into
`knowledge/` over time -- so "what do you know about my X" draws on real file
troves, not just the narrative layer.

**Exit criteria:**
1. GATE -- filename/path-PII sanitization enforced before any index hits `raw/index/` or a prompt.
2. GATE -- derived-facts sensitivity policy defined + applied (`sensitivity:` frontmatter).
3. GATE -- answer-landing contract pinned + implemented.
4. `personal.watched_folders` (local + smb) via config + migration; body-blind index for >=1 local and >=1 NAS root.
5. Producer `folder-deep-scan` (file-exists anchor) + `backends/folder.py` read-in-place, answer-only, verified on a real trove.
6. Dream/compile folds >=1 folder-derived fact into `knowledge/` live on lxw; trove-topic query returns a folder-sourced fact.
7. Staleness invalidation + failure/quarantine path covered by tests.

## Slices

Slice detail lives in per-slice `M027-S##-PLAN.md` files, created by
`ytstack:slice-milestone`. **Slice order MUST front-load the three GATE
exit-criteria (filename-PII rule, sensitivity policy, answer-landing contract)
before any broad `raw/index/` write or NAS read.** L is the lower-bound
skeleton; slicing will likely expand to 5-7.

- [ ] S01 -- (to be planned)
- [ ] S02 -- (to be planned)
- [ ] S03 -- (to be planned)
- [ ] S04 -- (to be planned)

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap`
checks if the plan still fits reality.

## How to update this file

- Flip slice checkbox `[ ]` -> `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` -> `status: done` and update global ROADMAP.md
