---
milestone: M005
project: llm-wiki
created: 2026-05-15T16:45:00Z
size: L
---

# M005 -- Context

## Goal

Personal task management lands on the wiki — `knowledge/people/` and `knowledge/projects/` pages adopt a two-layer **State + Timeline** shape with explicit `## Action Items` (Obsidian-Tasks-compatible) and `## Open Threads` sections, and `compile.py` extracts commitments from substrates (jamie / gmeet / email) and propagates them to the right entity page. Resolved items demote from State to Timeline on the next compile pass when the substrate contains resolution evidence.

## Exit criteria

1. `knowledge/people/` and `knowledge/projects/` articles render the two-layer shape (compiled-truth State block above `---`, append-only Timeline below) when `compile.py` runs over jamie / gmeet / email substrates.
2. Each entity page contains `## Action Items` with `- [ ]` checkboxes (Obsidian Tasks plugin syntax — `📅 due`, `⏫ priority`, optional `🔁 recurrence`) and `## Open Threads` as separate, distinct sections.
3. `compile.py` extracts commitments from at least the **jamie** and **gmeet** substrates and routes them to the right entity's Action Items / Open Threads. Email-substrate extraction is in scope but a stretch goal — drops to a per-substrate flag if it doesn't fit.
4. `scripts/lint.py` has a new `check_two_layer_pages` rule that flags entity pages missing the State / `---` separator / Timeline structure, and a `check_action_item_syntax` rule that flags malformed Obsidian-Tasks lines.
5. An Obsidian Dataview query in `knowledge/MOCs/inbox.md` (or similar new MOC) renders a cross-entity inbox view (`TASK WHERE !completed AND contains(file.path, "knowledge/people/")` or equivalent), giving the operator a single "what do I owe whom" surface.
6. `AGENTS.md` schema doc updated to describe the two-shape split (atomic for `concepts/qa/facts/connections/`, State+Timeline for `people/projects/`); 1-2 hand-picked existing person/project pages migrated to the new shape as canaries; templates updated.
7. **Lifecycle**: on the next compile pass after a resolution signal appears in substrate (e.g. "sent the Q3 deck to Jane" in a daily note or jamie meeting), the corresponding Action Item / Open Thread demotes from State to a Timeline entry with `[resolved]` marker and the source-substrate citation. Operator can also check off `- [ ]` → `- [x]` manually in Obsidian; compile preserves manual `[x]` state.
8. **Dashboard integration**: the existing Obsidian dashboard (M003-S01) surfaces the personal task layer — at minimum a "Today / Overdue / This Week" Dataview block + an open-count stat card. Optional: per-entity breakdown chart and a "Top 5 stale Open Threads" panel. Configurable via the same `cssclasses` + `templates/.obsidian/` convention used by the existing dashboard.

## Size

L — 4-5 slices, 11-20 tasks total. See `M005-ROADMAP.md` for slice breakdown.

## Decisions locked in discuss phase

- 2026-05-15: **No new top-level `tasks/` folder.** Tasks live inside `knowledge/people/` and `knowledge/projects/` entity pages, in `## Action Items` + `## Open Threads` sections within the State block. Aligns with gbrain (commitments as Fact-kind, embedded in entity pages); diverges from Karpathy/Cole only because their concepts don't cover tasks at all. Rationale and source verification in `.ytstack/backlog/entity-pages-state-timeline.md` and `.ytstack/backlog/gbrain-comparison.md`.
- 2026-05-15: **Obsidian-Tasks-plugin syntax is the canonical form.** `- [ ]` + inline `📅 due`, `⏫ priority`, `🔁 recurrence`. Operator gets free Today / Waiting / Inbox views via Dataview. No engine-side task-state machine.
- 2026-05-15: **Two shapes coexist, not migration.** `concepts/`, `qa/`, `facts/`, `connections/` keep their current atomic-article shape. Only `people/` and `projects/` adopt State+Timeline. Type-conditional in the compile prompt.
- 2026-05-15: **Extraction substrate priority: jamie > gmeet > email.** Meeting transcripts are the highest-density commitment source; daily mentions / email are stretch.
- 2026-05-15: **Dashboard surfaces the task layer as its own pane.** Reuses the existing dashboard infrastructure (Meta Bind buttons, Dataview, cssclasses-via-frontmatter, capture/run-button markers from M003-S01); no separate "tasks dashboard" file. Stat cards follow the established "honesty + positive framing" rule (no "0 X" framings).

## Open questions

- **Anchor folder for the first slice.** Start with `knowledge/people/` (highest substrate volume from jamie/gmeet) or `knowledge/projects/`? Decide at slice-milestone phase.
- **Entity resolution for "I'll send the deck" said by Jane in a meeting.** Lands on Jane's page (the speaker, owner of the commitment)? Or the operator's "self" page? Or the project page? gbrain's answer: propagate to all touched entity pages with attribution. Defer to slice-S02 design.
- **Timeline growth cap.** Defer to risk-mitigation (see `.ytstack/backlog/entity-pages-state-timeline.md`). Not in M005 scope unless a single canary page hits the limit during migration.
- **`raw/transcripts/jamie/` and `gmeet/` files don't carry attendee → entity-page wikilinks today.** First slice probably needs an attendee-resolution helper. Open: is this a substrate-side enrichment (collector writes `attendees:` frontmatter with resolved entity links) or a compile-time resolution against `knowledge/people/`?
- **Lifecycle edge case: operator manually checks `- [x]` in Obsidian but substrate has no resolution evidence.** Compile pass next time: preserve the manual `[x]` and demote to Timeline anyway, or leave it `[x]` in State indefinitely? Operator-friendly default: preserve `[x]` until the next State rewrite, then demote with `[manual-resolved]` marker.
- **Stretch: email extraction.** If jamie + gmeet ship cleanly, does the email substrate get the same extraction backend? Or is email-commitment extraction a quality-too-low signal (newsletter spam, automated mails) and explicitly out of scope?
