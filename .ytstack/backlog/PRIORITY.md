# Backlog Priority — post-M005

Snapshot 2026-05-15 after M005 closure. **Heuristic, not formal commitment.** Re-run after canary findings (`docs/m005-s03-canary-procedure.md`) shape real-world priority signal.

## ✅ Done — close these out

Already shipped; their backlog files describe historical context, not future work. Safe to leave (project memory) or move to `.ytstack/backlog/shipped/` if the dir gets too noisy.

- `entity-pages-state-timeline.md` — M005 entirely (`eb7da72`)
- `gmeet-collector.md` — M004 close (`4762a99`)
- `jamie-intake.md` — shipped via `scripts/collectors/jamie.py`
- `jamie-multi-tenant-lift.md` — shipped 2026-05-15 (per memory)
- `voice-intake.md` — recent parallel-session ship (`01b8dd3` + sibling commits)
- `health-collector.md` — Oura Phase 1 shipped (`1fd1044`); future phases stay backlog
- `dashboard-action-items.md` — subsumed by M005-S05's Personal Tasks pane (re-check before reopening)
- `screenshots-intake.md`, `youtube-intake.md` — shipped previously
- `compile-role-axis.md` — M007 entirely (`1022fd6`), 23 commits, all 5 exit criteria green
- `areas-bucket.md` — M008 (`3a445b7`), Agent A in parallel worktree
- `author-attribution.md` — M009 (`691d786`), Agent B
- `compile-60kb-plus-silent-fail.md` + `compile-per-call-timeout.md` + `compile-already-on-1m-fallback.md` — M010 reliability bundle (`b16a406`), Agent C
- `takes-substrate.md` — M011 (`ba63c1c`), Agent D; producer gated behind `features.extract_takes` until operator dogfoods
- `connection-quality.md` — M012 (`a16a01e`), Agent E
- `domain-frontmatter.md` — M013 (`04b4d6f`), Agent F

## ❌ Rejected — close

Explicitly rejected after audit; keep files as decision-context only.

- `lateral-linking.md` — Tag-Jaccard "Related" sections rejected after audit re-verify (`796e97e`)
- `meetily-intake.md` — rejected during Jamie eval (per `project_meeting_intake_candidates`)

## 🔥 Hot M006 candidates — small, contained, real value

Cheap to ship, no canary dependency, immediate quality-of-life lift.

- **`ytstack-hook-exit-code.md`** — `pre-tool-use-edit` hook bug surfaced during M005 (exit 2 blocks when intent was warn-only). Fix: hook returns exit 0 + stderr warning, OR `plan-task` skill auto-injects SUMMARY paths into Files section. ~half a day.
- **`compile-60kb-plus-silent-fail.md`** — real silent-failure surface in compile.py at ≥60 KB sources. Real bug, not aspirational.
- **`compile-per-call-timeout.md`** — `compile.py` lacks per-call timeout on SDK `query()`. Sibling to the 60kb fail.
- **`preflight-guard-rollout.md`** — extend the pre-flight prompt-size guard to remaining LLM call sites (small, mostly mechanical).
- **`watermark-on-failure-fix.md`** — sibling to a recent fix; check if already absorbed by parallel work.
- **`lx-vault-merge.md`** — Phase 0+1 ✓ (tarball `~/Archive/lx-vault-2026-05-16.tar.gz` + commit `cf8db73` in lxw vault repo). Phase 2 blocked on compile-role-axis (M007 in flight) + areas-bucket + entity-pages + author-attribution.

## 🌱 Medium — entity-page-layer extensions (M006 or M007)

The gbrain-pattern cluster that complements M005. Re-evaluate after canary signal — extraction quality on real substrate is the gating data.

- **`dream-cycle.md`** — scheduled cross-time synthesis (vs. per-file compile). Different from compile in that it synthesizes *across* the timeline. Cheapest validation: schedule it as a piggyback, see what it produces over a week.
- **`subtype-axis.md`** — split `concepts/` into 6 meaningful color groups for the graph view. Quality-of-life, not load-bearing.
- **`curiosity-consumer-gap.md`** — close the curiosity-loop consumer side (producer alive, consumer missing).
- **`curiosity-topic-as-search-query.md`** — use topic as IMAP/Gmail search-query, not blind folder dump.
- **`curiosity-dashboard.md`** — surface curiosity loop in dashboard.

## 🐌 Long-tail — substrate expansion + tooling debt

No urgency. Each adds capture surface; the wiki's value plateaus around 4-5 active substrates. Pick when an existing substrate becomes saturated and a real demand signal appears for one of these.

**Second-wave substrates:**

- `browser-history-collector.md`, `github-activity-collector.md`, `llm-transcripts-collector.md`, `calendar-collector.md` (note: `scan_calendar.py` exists; might be re-shape), `dms-collector.md`, `reading-highlights-collector.md`, `music-listening-collector.md`, `sunoflow-collector.md`, `nas-ingest.md`

**Tooling / docs / polish:**

- `architecture-deepening.md` (saturated walk per memory), `obsidian-plugin.md`, `use-llm-wiki-skill.md`, `vault-dashboard.md`, `dashboard-upcoming-events.md`, `distribution-strip.md`, `compiler-suggestions.md`, `collectors.md` (meta), `cleanup-followups.md`, `flush-orphan-recovery.md`, `imap-reader-and-gmail-strategy.md`, `prompt-aware-index-injection.md`, `postcompact-only-injection.md`, `readme-polish.md`, `seed-semantic-diff.md`, `wiki-correct-deferred.md`

**Doc-only (reference, not actionable):**

- `karpathy-comparison.md`, `gbrain-comparison.md` (architecture-comparison artifacts; keep)
- `architecture-scaling-2028.md` — 4-lever scaling sequence for `knowledge/` over 2-3 years (subtype-axis → MOC-first → lifecycle-tier → recursive-dream-cycle); MOC auto-maintenance flagged as the real bottleneck blocker. Anchors any future "knowledge/ is getting too big" discussion.
- `collectors.md` (meta doc)


## 📦 lx-vault-merge prerequisite stack (cross-references)

Items already listed above, grouped here to make the import-quality stack visible. Order in `lx-vault-merge.md` "Phase 2 quality stack".

**Schema (must-have):**
- compile-role-axis (M007 in flight)
- areas-bucket
- entity-pages-state-timeline
- author-attribution

**Quality (should-have):**
- takes-substrate — promoted from Medium → Hot for Phase 2 attribution fidelity
- connection-quality — promoted from Medium → Hot for cross-link quality
- domain-frontmatter (optional, parallel-shippable)

**Reliability (real Phase-2-run risks):**
- compile-60kb-plus-silent-fail
- compile-per-call-timeout
- compile-already-on-1m-fallback

**Post-Phase-2 (optional):**
- dream-cycle

Total prerequisite lift: ~14 dev-days. See `lx-vault-merge.md` for the rationale + ship order.

## Re-triage cadence

- After every milestone closes
- When a parallel session ships a feature whose backlog file says "deferred" (close the file)
- When a Hot candidate doesn't make a milestone for 2+ cycles (downgrade to Medium or reject explicitly)
