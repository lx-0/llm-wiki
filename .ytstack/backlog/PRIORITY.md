# Backlog Priority — post-M020 snapshot

Last reset: 2026-05-17 after M020 (backlinks footer) closeout, refreshed same day after the M019 doc-sync + drift-sweep + diagrams-badge-cleanup arc + 3 new study-arc backlog entries (+ 1 parallel-session entry, not mine). Inventory: 52 open · 30 shipped (`shipped/`) · 2 rejected (`rejected/`). (2026-05-22: distribution-strip shipped via sparse-checkout; study-piggyback-audit done — wiring OK.)

**Heuristic, not formal commitment.** Re-evaluate after every milestone close. When a file ships, `git mv` it into `shipped/`; when explicitly rejected, into `rejected/`. Keep the working directory short — agents glance at this list to find the next move.

## 🔥 Hot — small, contained, ready to ship

Pick one when "next?" comes up and the operator wants a concrete tick.

- **`study-run-due-piggyback-audit.md`** — verify the M019 daily-schedule piggyback actually fires on lxw (enabled in vault, default-off in engine). 30-min audit; ripens 2026-05-19 to 2026-05-23 so week-1 review has clean data. **Audited 2026-05-22: wiring works (fires/spawns/cooldown OK, run_count=8); the doc's "daily" premise was wrong — manifest is `schedule: weekly`, so the runs-gap is expected. No fix needed; close it.**
- **`ytstack-hook-exit-code.md`** — `pre-tool-use-edit` hook exits 2 when intent was warn-only. Half-day fix or plan-task skill change.
- **`voice-punctuate-followups.md`** — end-to-end test + optional pre-2026-05-17 backfill + quality observation window.
- **`pictures-followups.md`** — HEIC ingest path untested, archive-policy decision deferred (iCloud footprint).
- **`stg-glob-pattern.md`** — Firefox STG backup dir versions; glob support so engine doesn't pin a single version.
- **`voice-openwhispr.md`** — OpenWhispr v1.7.0 stores transcripts in SQLite, not files. Reader-kind for voice collector.
- **`flush-orphan-recovery.md`** — recovery for orphan flushes (check current state).
- **`preflight-guard-rollout.md`** — extend pre-flight prompt-size guard to remaining LLM call sites.

## 🌱 Medium — design clarified, blocked or waiting on signal

Real value, real cost; needs canary data, parallel-session coordination, or operator green-light.

- **`health-trend-synthesis.md`** — MVP SHIPPED 2026-05-23 (`wiki health-trends`, deterministic $0 aggregation → `## Trends` block in `concepts/health.md`). Deferred future layers: LLM narrative, cross-substrate correlation, MOC hub, charts.
- **`concept-consistency-routine.md`** — SHIPPED all 5 phases (`wiki reconcile`, autonomous fact-violation reconciliation; folded into the architecture.excalidraw Hard-Facts band). Default-off; awaiting operator opt-in + first live `--apply` run.
- **`compile-agent-no-filesystem-write.md`** — return structured payload via `ResultMessage`, write deterministically in `compile.py`. Was the M018-S03 vision before that slice got cancelled; full requirements in `commit-article-manifest.md`.
- **`commit-article-manifest.md`** — re-arch plan for `commit_article` after M018-S03 cancel (knowledge-writes are agent-side via SDK tool-use, not pure I/O extractable).
- **`search-tools.md`** — M020-deferred axis-aware `wiki search --type --domain --author` + temporal `wiki recent`. Re-evaluate when vault crosses ~3k articles or dream-cycle/curiosity surface a real query bottleneck.
- **`recursive-session-summary.md`** — flush-context Phase 2 (hierarchical summarisation). Deferred 4-6 wks after gen-2 budgets prove out.
- **`personality-substrate-predigestion.md`** — gating IPIP-NEO-120 / HEXACO-60 / PID-5 behind pre-digestion. M019 follow-up; not blocking the wedge. **The natural next M019-arc milestone** once the week-1 review confirms the wedge is operationally useful.
- **`olbi-coverage-optimization.md`** — OLBI is the highest-cost ($0.28) + lowest-coverage (37.5%) instrument on the manifest. Three mitigation paths laid out (operator-input / Exhaustion-only fork / Sonnet override). Decision belongs in the 2026-05-24 week-1 review.
- **`pass2-dashboard-widget.md`** — dashboard pane surfacing the latest Pass-2 cross-study finding. DECISIONS.md flagged as M019 closeout deferred. Ripens after first Pass-2 cycle (~within a week of 2026-05-24).
- **`lx-vault-merge.md`** — Phase 2 (longform import + cross-vault link reconciliation). Phase 0+1 ✓; Phase 2 unblocked by M007/M008/M009 ships.
- **`interactive-cli.md`** — Python interactive-menu shipped (`scripts/menu.py`); this is the broader CLI UX vision.
- **`m005-infographics-extension.md`** — deferred parts only after the 2026-05-15 wrapup doc-gap pass.
- **`subtype-axis.md`** — split `concepts/` into ~6 color groups for the graph view. Quality-of-life, not load-bearing. Re-evaluate after dream-cycle output shape stabilises.
- **`obsidian-app-json-smart-merge.md`** — concrete: smart-merge `.obsidian/app.json` so `wiki seed --force` doesn't overwrite operator preferences.
- **`compiler-suggestions.md`** — suggestion sweep originating from compile-time observations (status TBD on re-read).
- **`postcompact-only-injection.md`** — optional optimization on the 2026-05-05 pointer-block refactor.
- **`prompt-aware-index-injection.md`** — optional/configurable feature, evaluate after SessionStart matures.
- **`wiki-correct-deferred.md`** — `wiki correct` CLI followups.
- **`curiosity-dashboard.md`** — dashboard pane for curiosity-loop output.
- **`curiosity-topic-as-search-query.md`** — use curiosity-topic as IMAP/Gmail search-query, not blind folder dump.
- **`dashboard-action-items.md`** — likely subsumed by M005's Personal Tasks pane (verify before reopening).
- **`dashboard-upcoming-events.md`** — was blocked on calendar-collector; M006 shipped, so now unblocked.

## 🌾 Collector ideas — large pool, pick when capacity allows

Each one is a substrate collector; same shape as the 11 already shipped. None is hot; ship when the substrate's input grows enough to be worth wiring.

> **Consumption/curiosity axis (2026-05-22 reframe):** `music-listening`, `youtube-intake` (watch-history), `browser-history`, `reading-highlights` cover one persona-axis — the non-work self that work-substrate misses. Per `.ytstack/DECISIONS.md` 2026-05-22, value them by *blindspot-coverage*, not signal-density; `music-listening-collector.md`'s "weight-low correlation-ribbon" framing is superseded. Pick by axis-coverage (steep diminishing returns stacking channels) and gate on a synthesis consumer existing. Cluster doc + sequencing: `consumption-curiosity-axis.md`. (Suno = production axis, not this one.)

- **`screenshots-intake.md`** — Tier 3+4 still open (Tier 0-2 shipped).
- **`youtube-intake.md`** — T3-cloud + curiosity-loop + dashboard open (T0-T3-local shipped).
- **`imap-reader-and-gmail-strategy.md`** — generic IMAP shipped; internal-OAuth-app strategy doc.
- **`browser-history-collector.md`** — Firefox/Chrome history → raw/notes/browser/.
- **`github-activity-collector.md`** — issues/PRs/comments → raw/notes/github/.
- **`reading-highlights-collector.md`** — Readwise/Kindle/Pocket → raw/notes/highlights/.
- **`music-listening-collector.md`** — Spotify/Apple Music → raw/notes/music/.
- **`llm-transcripts-collector.md`** — Claude/ChatGPT export → raw/transcripts/llm/.
- **`dms-collector.md`** — Slack/iMessage/WhatsApp → raw/notes/dms/.
- **`nas-ingest.md`** — local NAS file-tree as substrate.
- **`sunoflow-collector.md`** — Suno music-generation history (2026-05-15 self-cartography arc).

## 📚 Research / cluster / forward-looking

Living docs, not actionable wedges. Read when adjacent work surfaces them.

- **`architecture-deepening.md`** — 13 candidates + 6 M003 framings (do NOT re-run `improve-codebase-architecture`).
- **`architecture-scaling-2028.md`** — 4-lever sequence for 5k+ articles (subtype-axis → MOC-first → lifecycle-tier → recursive-dream-cycle).
- **`gbrain-comparison.md`** — gbrain pattern lift (entity-pages + takes + dream-cycle all shipped from this cluster; remaining ideas live here).
- **`karpathy-comparison.md`** — Karpathy-pattern comparison cluster.
- **`collectors.md`** — parent collector-pattern doc.
- **`vault-dashboard.md`** — original vault-UX design doc; M003 dashboard shipped most of it.
- **`obsidian-plugin.md`** — engine-as-plugin idea (ready, not actionable now).
- **`seed-semantic-diff.md`** — semantic-diff for `wiki seed` operator-preference preservation.
- **`readme-polish.md`** — deferred README polish items pending engine stability.
- **`cleanup-followups.md`** — accumulated cleanup notes.

## ✅ Done — in `shipped/`

29 files moved 2026-05-17. M005-M020 + ad-hoc arcs: areas-bucket, author-attribution, calendar-collector, compile-{60kb, 1m-fallback, per-call-timeout, role-axis, scope-allowlist}, connection-quality, curiosity-consumer-gap, domain-frontmatter, dream-{cycle, priority-config, sampled-activation}, entity-pages-state-timeline, gmeet-collector, health-collector, jamie-intake + multi-tenant-lift, m019-diagrams-update, m020-infographic-update, operator-self-reports, producer-seam, python-interactive-menu, takes-substrate, use-llm-wiki-skill, vault-health-doctor, watermark-on-failure-fix, agents-template-scanner-resync.

## ❌ Rejected — in `rejected/`

`lateral-linking.md` (Tag-Jaccard "Related" rejected after audit re-verify) · `meetily-intake.md` (rejected during Jamie eval).
