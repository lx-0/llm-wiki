---
milestone: M005
project: llm-wiki
size: L
created: 2026-05-15T16:45:00Z
status: planned
total_slices: 5
completed_slices: 4
---

# M005 Roadmap

**Goal:** Personal task management lands on the wiki — `knowledge/people/` and `knowledge/projects/` pages adopt a two-layer State+Timeline shape with `## Action Items` (Obsidian-Tasks-syntax) and `## Open Threads` sections, compile.py extracts commitments from jamie/gmeet/email substrates and propagates them to the right entity page, and the existing Obsidian dashboard surfaces the task layer as its own pane.

**Exit criteria:**
1. Two-layer State+Timeline rendering for `people/` + `projects/` during compile.
2. `## Action Items` (Obsidian-Tasks-compatible `- [ ]` + 📅) and `## Open Threads` as separate State-block sections.
3. Compile extracts commitments from at least jamie + gmeet; routes to right entity.
4. `lint.py` checks for two-layer shape + Action-Item syntax.
5. Dataview-based cross-entity inbox MOC.
6. AGENTS.md + templates updated; 1-2 canary pages migrated.
7. Lifecycle: resolved items demote State → Timeline on next compile when substrate has resolution evidence; manual `[x]` preserved.
8. Dashboard pane: Today/Overdue/This Week Dataview + open-count stat card (+ stretch: per-entity chart, stale-Open-Threads panel).

## Slices

Slice detail lives in per-slice `M005-S##-PLAN.md` files, created by `ytstack:slice-milestone`.

- [x] S01 — Schema + compile-prompt branching (two-layer for `person|project`, canary migration) — 4 tasks — `M005-S01-PLAN.md`
- [x] S02 — Lint + structural checks (`check_two_layer_pages` + `check_action_item_syntax`) — 3 tasks — `M005-S02-PLAN.md`
- [x] S03 — Substrate extraction (jamie + gmeet commitments → entity pages) — 5 tasks — `M005-S03-PLAN.md`
- [x] S04 — Lifecycle (resolution demotion + manual-`[x]` preservation) — 4 tasks — `M005-S04-PLAN.md`
- [ ] S05 — Dashboard pane + cross-entity Inbox MOC — 4 tasks — `M005-S05-PLAN.md`

## Tentative slice arc (refine in slice-milestone)

- **S01 — Schema + Compile-Prompt branching.** Add type-conditional rule to `prompts/compile_main.md`: for `type: person|project`, emit the two-layer shape with `## State`, `## Action Items`, `## Open Threads`, `---`, `## Timeline`. Pass-through for other types. AGENTS.md schema doc updated. One canary `knowledge/people/` page hand-migrated to lock the spec.

- **S02 — Lint + structural checks.** New `check_two_layer_pages` in `scripts/lint.py`: for `type: person|project`, assert State block + Action Items section + `---` + Timeline section + Timeline reverse-chronological. New `check_action_item_syntax`: validate Obsidian-Tasks lines. Tests on the canary + a deliberately broken fixture.

- **S03 — Substrate extraction (jamie + gmeet).** Compile-time commitment extraction: when processing a `raw/transcripts/jamie/*.md` or `raw/transcripts/gmeet/*.md`, the LLM identifies action items (Task / Owner / Deadline / Context quartet) and routes them. Entity resolution: speaker → `knowledge/people/<slug>.md`, mentioned project → `knowledge/projects/<slug>.md`. Action items land in the State block; the substrate citation lands in Timeline.

- **S04 — Lifecycle (resolution demotion + manual-check preservation).** Compile reads existing State Action Items / Open Threads before rewriting. When next-pass substrate contains resolution evidence (semantic match via prompt rule), the item demotes to a Timeline entry with `[resolved]` marker. Manual `- [x]` in operator-edited Action Items is preserved across compile runs; explicit demotion happens only on the next State-rewrite touch. Edge case: orphan State items (no substrate evidence either way) stay until manually closed.

- **S05 — Dashboard integration + cross-entity Inbox MOC.** Extend the existing Obsidian dashboard (M003-S01) with a "Personal Tasks" pane: Dataview `TASK WHERE !completed` filtered by `path:knowledge/people OR path:knowledge/projects`, grouped by Today / Overdue / This Week. Open-count stat card (paired with a context stat — total entities or commitments-extracted-this-week — to follow the honesty + positive framing rule). New `knowledge/MOCs/inbox-tasks.md` as a standalone cross-entity inbox view that the dashboard pane links to. `templates/.obsidian/` updated so the pane survives `wiki seed`.

## Run order

Slices execute sequentially. After each slice, `ytstack:reassess-roadmap` checks if the plan still fits reality. Likely reassess gates: after S02 (do we need any S01 prompt-rule revisions before extraction work?), after S03 (is jamie+gmeet extraction quality good enough to justify lifecycle work, or do we tune the extraction prompt first?), after S04 (does the dashboard scope still fit, or does dogfooding on real action items change what we want to render?).

## How to update this file

- Flip slice checkbox `[ ]` → `[x]` when its tasks are all `summarize-task`-confirmed
- Update `completed_slices` count
- On milestone completion, flip `status: planned` → `status: done` and update STATE.md `current_milestone`
