# Backlog Priority — reconciled against the code, 2026-10-15 (M033 close)

Inventory: **80 reconciled** → 3 moved to `rejected/` (superseded), **77 still in the working
set** (40 open · 37 partially done). Nothing had shipped silently since the M032 pass.

**How this pass ran (M033-S05-T06).** Eight read-only agents re-derived every item from the
CODE — scripts/, tests/, git log, the live vault read-only — not from what the item says
about itself. Every superseded / stale-premise verdict, and every premise-shifting one, went
through a separate refutation agent before it was filed. A wrong "done" deletes real work
from the radar, so the refuter corrected four verdicts: `subtype-axis` from stale premise
to superseded, `cleanup-followups` from partial to superseded, `dashboard-upcoming-events`
from partial to open, and the residue of `obsidian-plugin`.

**Fixed on the way.** The audit turned up defects no item named; each was fixed with a test
watched failing first and released as 0.7.1–0.7.3:

- calendar rollups lost the unchanged events of every date an incremental run touched (one
  live date 6 → 1);
- the suggestion pass wrote anywhere in the vault over third-party mail;
- seven `.md` suggestions were invisible;
- the reports never read voice, because the globs were dead (sessions stay out: ~434K
  tokens / 14 days);
- the desktop's Review row crashed on `termios.error`;
- screenshot sidecars named the wrong model;
- a piggyback-runner signal race;
- `optimize_claude_md` staged into a missing folder with unscoped edits;
- two gaps in the by-path doc guard, plus seven stale docs.

The lines below are written after those fixes.

Effort: S = hours · M = a day or two · L = a milestone. `·partial` means some phases shipped
and the sentence names only what remains.

## 🔥 Hot — high value, ships in hours or days

- **`flush-orphan-recovery.md`** (S) — Sweep the `sessions/` root: stale staged files go through a newest-per-session collapse and back into flush, and doctor + dashboard count them (both count `failed-flushes/` only). Live: 37 staged files, all older than 30 days, and a sampled session (staged 2026-09-14) is in neither daily/ nor the archive — lost silently. Safer than the file assumed: `_record_flush` now runs after the delete and `append_to_daily` replaces in place.
- **`flush-extract-outage.md`** (S ·partial) — Root causes fixed; the drain is left: collapse `failed-flushes/` to the newest context per session_id before retrying (live: 358 contexts from 47 sessions, one with 56 copies) and drain on a depth-proportional cadence of its own instead of 5 per 24 h after a successful flush or compile.
- **`curiosity-request-dedup.md`** (S) — The per-(account, folder) supersede pass (preview, `--apply`, the new status excluded from `_pending`) plus a producer-side skip while a request for the folder is pending; every duplicate costs a compile and a suggestion SDK pass.
- **`recursive-session-summary.md`** (M) — Its own trigger fired: 23 of 37 staged and 218 of 358 failed flushes carry the truncation marker (2026-05-24 → 10-15), assistant prose dropped before it reaches daily/. Build the summariser on the background flush path (not inside the 10 s hook), a findings-survive fixture, token accounting.
- **`compiler-suggestions.md`** (M ·partial) — Write scope and `.md` visibility fixed at the M033 close. Left: an executor branch for `extend-rule` (the type the prompt calls preferred), IMAP error / dry-run output + a `failed` status, `_audit.log`, `dry_run` / `estimated_count` with a pre-move recount, a guard against rewriting the filter file while Thunderbird runs, existing rules as prompt input. 21 actions sit pending in the live vault.
- **`llm-transcripts-collector.md`** (M ·partial) — Rewrite the file around what is dark, privacy first: secret / denylist redaction on the shipped session-hook path does not exist (358 unredacted staged contexts live), then the claude.ai / ChatGPT ZIP drop-folder, Cursor (verify the installed hooks parse; `state.vscdb` for history), an optional pre-hook JSONL backfill. Phase 1 is delivered by the hooks + flush.
- **`preflight-guard-rollout.md`** (S ·partial) — Compile and query are guarded; wire `assert_prompt_within_budget` into `suggestions/producer.py` and `optimize_claude_md.py` (+ the knob and its migration; one shared or per script is undecided), and into the reports runner — off-manifest ASRS-v1.1 would send ~835K tokens of health notes over its 180-day window.
- **`orphan-check-footer-masking.md`** (S ·partial) — Footer-aware counting shipped, the check still cannot fire: index membership exempts a page and `sync_index` appends every article on every compile. Decide whether index membership still counts, then re-baseline on the real vault.
- **`index-md-drift.md`** (S ·partial) — Strip "append a row to knowledge/index.md" from the compile_calendar / daily / default / pictures / screenshots and query_file_back prompts; the engine reconciles index rows deterministically now.

## 🏔 Big rocks — high value, milestone-sized

- **`deslop-arc.md`** (L ·partial — M032 + M033 shipped, **M034 next**) — Python owns the dispatch (`wiki` ≤ 150 lines with one process hop; today 851 + 1,827 lines of bash), one table for `wiki help` and the menu, README ≤ 300 (378), the TUI's ✨ and commit hash gone; plus the `print` → console move and the two inherited registry items below. Measured close-out numbers live in §6 of the file.
- **`architecture-scaling-2028.md`** (L) — Lever 2/3 triggers fired (live: index.md 2,272 rows / 1.28 MB, 2,273 articles, `concepts/` 2,078 flat files; the ~157K-char compact index is embedded per compile source, query, suggestion pass). Lever 1 is retired (see the file); split the meta-entry into moc-auto-maintenance / lifecycle-tiering / recursive-dream files and build Lever 2 (MOC upkeep + MOC-first retrieval).
- **`system-level-scheduler.md`** (M ·partial) — The clock: `wiki flush --piggybacks-only`, a LaunchAgent / systemd template, `wiki scheduler {install,uninstall,status}`, the SessionEnd double-fire question — so a Claude-Code-free week no longer freezes every collector.
- **`reading-highlights-collector.md`** (M) — The first consumption channel (`consumption-curiosity-axis.md`'s own sequencing): decide Readwise vs direct sources, then collector + adapter, per-book `raw/notes/highlights/`, watermark, a multi-tenant `personal.accounts.<id>.reading` key + migration.
- **`consumption-curiosity-axis.md`** (L ·partial) — No consumption channel exists; its synthesis consumer is live (dream's theme sections on the operator page, corpus keyed on a slug mention or `author:`). After the first channel: the passive-feed engagement filter and the sensitivity posture before a second one.
- **`browser-history-collector.md`** (M ·partial) — `scan_browser` predates the item and reads one Chrome profile as a manual snapshot (the live vault's only report is from 2026-04-12): build the multi-profile Chromium reader, the per-profile watermark + filtered daily history rollup, `keyword_search_terms`.
- **`screenpipe-intake.md`** (L) — The collector is unbuilt (DB, episodes, the 3-stage audio gate, PII redaction, a source-only rollup, a multi-tenant key + migration, a setup doc). Capture itself has stopped again: `~/.screenpipe/db.sqlite` (5.6 GB) last written 2026-09-24, only the watchdog LaunchAgent loaded (operator infra).
- **`dms-collector.md`** (L) — Nothing built; the Phase 1 Telegram wedge covers a persona region produced daily, and its consumer (entity pages with State + Timeline) is live.
- **`operator-financial-operational-fact-layer.md`** (M ·partial) — Plumbing shipped; left: the PII policy (which derived figures may become facts), operator-finance + company master-data facts with as-of dates, and a consumer for `sensitivity:` — nothing enforces it and `wiki publish` mirrors `knowledge/` unfiltered.
- **`sunoflow-collector.md`** (M) — The account-bound collector: Phase 1 songs on a `createdAt` watermark, Phase 2 the daily play rollup (no longer blocked upstream; check the deployment).
- **`personality-substrate-predigestion.md`** (L) — All six slices (summarisation cache, per-item `scope:`, per-batch audit, IPIP-NEO-120 / HEXACO / PID-5 / PVQ). It is now also what lets sessions into the clinical scope: the audit stub reads the real paths and shows the true load (sessions ~3.3M tokens over 180 days).
- **`nas-ingest.md`** (M ·partial) — M027-S06: the smbprotocol reader into `raw/index/<root>.md`, out-of-sandbox body reads, a periodic run, one e2e on a real share (`kind: smb` validates but is skipped).
- **`compile-agent-no-filesystem-write.md`** (L ·partial) — The hook gate closed the incident path; left are the structured-payload + deterministic-writer refactor and the substrate-injection replay test. **Merge with `commit-article-manifest.md`** — the same work.
- **`commit-article-manifest.md`** (L) — The manifest half of the same refactor (validated multi-target manifest, per-file ops, Python `commit_article`); no forcing blocker. Merge into the item above.

## 🌱 Medium

- **`lazy-collector-registry.md`** (M · M034) — A name → module table with lazy registration (collectors / preprocessors / producers); retire the workaround entry scripts.
- **`collect-flags-one-verb.md`** (S · M034) — `wiki collect <name> -- …` passthrough into the four collectors' `main(argv)`, then delete the three by-path entry scripts and PROCESS.md's second form.
- **`obsidian-plugin.md`** (M ·partial) — Don't build the plugin (desktop app + Obsidian dashboard cover status, queues, commands). Left, GUI-side: approve / reject + a pending count for suggestions (the CLI already works without a TTY), a non-interactive curiosity reject, a retry trigger for failed flushes (listed in the Obsidian dashboard, a count in the desktop); the desktop's Review row now refuses cleanly but is still a dead row.
- **`curiosity-dashboard.md`** (M ·partial) — Non-interactive accept / reject subcommands + desktop request cards (rationale, cost), the executed / failed / dismissed lifecycle, cost estimates, per-request provider, the pre-resolve step.
- **`home-screen-ux.md`** (M ·partial) — Lever 3: freshness checks on the doctor's `_ALL_CHECKS` + the missing probes (folder-index, per-collector inboxes, dedup, takes, web-research, studies).
- **`desktop-learnability-residue.md`** (M) — The operator decision on non-dispatchable Health checks (the desktop counts them all as issues), a vocabulary pass over the engine titles, a click-through task script in the shots harness.
- **`olbi-coverage-optimization.md`** (S) — Voice now reaches the instruments; sessions wait for the predigestion layer (above), then re-measure OLBI coverage and pick a path (path 1 uses the shipped `wiki study answer`).
- **`curiosity-topic-as-search-query.md`** (M) — An optional `query` on `MailboxReader.scan_deep` (gmail / imap; mbox as fallback), `query_terms` in the producer schema + prompt, passed through `backends/email.py`; sequence it against curiosity-request-dedup.
- **`architecture-deepening.md`** (L ·partial) — Every writing SDK call is on the harness now; open: the four read-only hand-rolled loops (#3), async Ollama (#10, M021-S02), the hook harness (#7), JSON log mode + the two hook `basicConfig` calls (#9), a markdown helper (#11), tz helpers (#13), atomic dashboard writes (#15; its one-shared-file premise is stale).
- **`deepening-arc-followups.md`** (M ·partial) — ~20 residues: doc drift (PROCESS.md:295/301/894, cli.md:305/440), phantom help (`dream-entity --cost-cap`, analyze's flags), study.py's own try-lock, Thunderbird bare continues, the wizard's hardcoded model list, the folder-index scheduling decision, polish. The calendar watermark item is moot (retired).
- **`correct-apply-overreach-and-partial-runs.md`** (M ·partial) — Defect A (a subject-vs-reference rule fed by the engine's primary / mention split), B2 an idempotent re-run (skip already-superseded files), B3 the delta manifest on the failure path; B1 shipped.
- **`listener-lifecycle.md`** (M ·partial) — Autostart provisioning from a template, the installed / TCC-ungranted axis, per-install listener config (registry.ts is hardcoded), a CLI / menu / doctor surface, a LaunchAgent core shared with the scheduler.
- **`dashboard-action-items.md`** (S) — A recency-windowed DataviewJS block reading `daily/*/sessions.md` (sessions left `daily/<date>.md`), PROCESS.md, the template resync.
- **`dashboard-upcoming-events.md`** (S) — The blocker is gone and the rollups now hold every future event once; build the Upcoming block (DataviewJS over the `## HH:MM–HH:MM · Title` headings, or `Key::` fields in the renderer) and decide 7 → 14 future days (+ migration).
- **`health-trend-synthesis.md`** (M ·partial) — LLM narrative, a `MOCs/health.md` hub, sparklines, cross-substrate correlation.
- **`music-listening-collector.md`** (M) — Last.fm adapter + rollup collector + config / migration + templates, once the operator confirms scrobbling.
- **`prompt-aware-index-injection.md`** (M) — A UserPromptSubmit hook + its registration in lib/agents.sh, the `hooks.prompt_aware_injection` keys + migration, DE / EN stopwords — after the item's observation preconditions.
- **`wiki-correct-deferred.md`** (M ·partial) — Paraphrase-aware fact lint on local Ollama, `correct add --apply`, a facts view in the dashboard / desktop.
- **`gbrain-comparison.md`** (M ·partial) — The three headline patterns shipped; left: RESOLVER.md per `knowledge/<type>/` + its lint, an IR eval bench (`evals/queries.jsonl` + P@5 / R@5 replay).
- **`collectors.md`** (L ·partial) — Umbrella: only Downloads watcher, LinkedIn, RSS / articles and bookmark → raw/articles have neither code nor a file of their own; give them files, then retire the umbrella.
- **`collector-loop-quirks.md`** (S ·partial) — The calendar half went with the 0.7.1 rewrite (the window is computed once per account); left: `gmeet._merge_group` logs the number of Docs actually merged + a test for a break on the second Doc (dormant).
- **`token-usage-accounting.md`** (S ·partial) — Breaks the DECISIONS rule on dollar figures: compile's "cost: $X", analyze.py, study.py and the reports runner still print SDK dollars, `templates/_dashboard-stats.md` seeds "LLM spend $0.00"; the per-entity dream token ceiling was never added.
- **`stg-glob-pattern.md`** (S) — A glob-aware resolver for `personal.stg_backup_dir` (newest matching dir) in scan_tabs + scan_browser, a test, docs; the miss is silent (a stale backup stamped with today's date).
- **`screenshots-intake.md`** (S) — E an app-name enum (`format=` schema on `chat_vision`), F a closed-world project guard, G a per-run `_runs/<slug>.json` vision log; drop H (thumbnails replaced it). The model stamp is fixed for new sidecars; up to 383 old ones keep `gemma4:e4b`.
- **`voice-openwhispr.md`** (M) — Confirm OpenWhispr's file export (path A) or build a `kind: openwhispr-sqlite` reader (path B); fix docs/setup-voice.md:198.
- **`imap-reader-and-gmail-strategy.md`** (S ·partial) — Shipped and live; relocate the org-side Internal-OAuth-app note into a setup doc, then file it to `shipped/` (the config.md contradiction it named is fixed).
- **`gmail-personal-consumer-account-gap.md`** (S · blocked on the operator) — The imap backend forces OAuth for any Gmail host (no App-Password fallback for the suggestions' actions), and the doctor offers a sign-in that 403s under an org-internal OAuth client — whether to hide it for consumer accounts or ship a second client is a design call.
- **`company-brain-federation.md`** (L) — A `scope:` frontmatter axis, a fail-closed human-approved promote channel, cross-vault identity + multi-author reconciliation; the office-hours has not happened.
- **`agent-apply-channel.md`** (L) — The office-hours validation, then a `wiki apply` verb (one structured-claim op first), a claim id that survives recompile, and a keep-or-overwrite rule for agent-applied content.
- **`github-activity-collector.md`** (L) — The whole collector; lower value than filed, because session flush already covers the coding narrative.
- **`publish-asset-channel.md`** (L) — The binary / JSON asset channel (blocked on the upstream context-mcp contract), the operator's sanitize-or-accept call on the four secret-gated files (still key-shaped spans live), the one-time reach test.

## 🧊 Low — real, not urgent

- **`backfill-voice-rollup-shape.md`** (S) — The backfill builds its voice line via `daily_capture.rollup_line` with `sources:` provenance; `append_with_source` needs a vault root first; re-pin the parity test.
- **`codex-distill-verbose.md`** (S) — Flush-prompt guidance for tool activity, a touched-file list instead of patch text for `apply_patch`, a smaller tool budget for tool-heavy sessions.
- **`correct-apply-edited-underreport.md`** (S) — Option 2 (derive edited / superseded from the delta and stop echoing the agent's lists) or close as option 3; option 1 was tried before filing.
- **`dev-checkout-root-dir-inference.md`** (M) — A `WIKI_VAULT` override or a checkout refusal for the Python entry points; the test fence repoints only `DAILY_DIR` (85 modules import `core.paths` by value).
- **`dream-insufficient-corpus-backoff.md`** (S ·partial) — Option 1 shipped; left: the v2 fast-reset (a mention-count snapshot) and optionally option 2 (generic-noun precision).
- **`gmeet-email-discovery-infographic.md`** (S) — `architecture.excalidraw`'s gmeet box lacks the email-discovery source; the overview has only a chip.
- **`intents-seen-state-shape.md`** (S) — `{"seen": [...]}` via `store_for` + the legacy migration + drop the allow-list entry.
- **`lx-vault-merge.md`** (S ·partial · operator) — Phase 2 ran (lxw 555b100e); Phase 3 is the operator's: decide on `lxw/imported/lx/` (104 files, 51 pages cite it), delete the iCloud `lx/` vault after re-checking the tarball, a DECISIONS dissolution entry.
- **`m005-infographics-extension.md`** (S ·partial) — Annotate the two-layer people / project shape in vault-tour.excalidraw; the task lifecycle + entity page → dashboard flow in architecture.excalidraw.
- **`m019-week-1-review.md`** (S ·partial) — Keep or revert the ISI Sonnet override from the 24 runs on disk; record it in DECISIONS, instrument.yaml and the manifest notes.
- **`memories-decision-doubt.md`** (S ·partial) — `raw/memories/` as substrate in the infographics, the operator's signal-to-noise review of Mode-B concepts, whether `compiled_from_distilled` needs a reader.
- **`obsidian-app-json-smart-merge.md`** (S ·partial) — Guard `seed --force` for a drifted app.json without an overlay, union semantics for `userIgnoreFilters`, tests.
- **`pass2-dashboard-widget.md`** (S) — `dashboard_reports.py`, the `_dashboard-reports.md` cache, the dashboard pane + refresh hooks; no desktop reports surface either.
- **`pictures-followups.md`** (S) — A HEIC test or recorded run, the archive policy (sources now move into `raw/inbox-mobile/pictures/`), pictures in the diagrams, a test of the `picture-batch` route.
- **`postcompact-only-injection.md`** (S) — Read the hook input's `source` and skip non-compaction starts, the `hooks.session_start.inject_on_sources` key + migration, the precondition checks.
- **`readme-polish.md`** (S) — A hero cast / GIF of a real setup → status → compile run; "trusted by" and a community link wait on adopters.
- **`relativize-wikilinks-followups.md`** (S) — The relativize pass and the `wiki links` audit walk `knowledge/` only — extend them to `raw/notes/longform/` source-and-final pages (no damage today: 16 bare links); sub-items 2 / 3 are operator triage.
- **`report-engine-version-stamp.md`** (S) — Literal M019 ids still stamp reports (runner.py:255, render_summary.py:360, analyst.py:299 / :363); one helper (pyproject version + short SHA) for all four writers + a test, once the field's fate is decided.
- **`search-tools.md`** (S) — `wiki search` + `wiki recent` stay deferred until ~3k articles (live 2,273) and a recurring need.
- **`seed-semantic-diff.md`** (S ·partial) — `--check` still flags graph.json UI state (collapse-*, showOrphans, textFadeMultiplier): a per-file engine-relevant subset or ignored keys + a `--check` test.
- **`vault-dashboard.md`** (S ·partial) — `state/history.jsonl` is written with no reader and heatmap-calendar is enabled with no heatmap — add the readers or drop both; the S07 MOC-suggestion stage is unbuilt.
- **`voice-punctuate-followups.md`** (S ·partial) — An optional backfill over pre-2026-05-17 notes + a `_punctuate` fallback unit test.
- **`youtube-intake.md`** (L ·partial) — T3-cloud (Gemini + cost guardrails), scene-change sampling, `--upgrade` / `--provider`, per-channel tiers, the curiosity upgrade loop, Tier 4; two docstrings still call T3 backlog.

## ⚰️ Moved to `rejected/` on 2026-10-15 — superseded, each verdict refuted first

- **`rejected/karpathy-comparison.md`** — Nothing to build: docs/PRINCIPLES.md publishes the lineage (dc08cfc), query results persist (`--file-back`), lint has the contradiction check. Only the naive-PKM comparison tables and the 8-step migration guide exist nowhere else — optional docs salvage.
- **`rejected/subtype-axis.md`** — Superseded for its only consumer, the graph view (domain-tag colour groups + Extended Graph's type → shape); DECISIONS had filed it so already. `architecture-scaling-2028.md` Lever 1 now says so. The colour residue (1,237 concepts without a graph-coloured domain tag) belongs to the domain-tag lint.
- **`rejected/cleanup-followups.md`** — No engine work: a doctor check would only ever find ten inert `.gitignore` lines in one vault and a canvas that does not exist; the SDK-verification bullets are answered by the live error logs and `wiki doctor`; the dead Excalidraw / seed / sync-memories pointers in KNOWLEDGE were fixed.

## How to keep this honest

Re-reconcile at every milestone close, and re-derive from the code — a backlog item
describes the world on the day it was written. When something ships, `git mv` it into
`shipped/`; when it is rejected, into `rejected/`. An item not listed here is invisible
to anyone glancing for the next move, so every file left in the working set must appear
in one of the live sections above — check with:

```sh
comm -23 <(ls .ytstack/backlog/*.md | xargs -n1 basename | grep -v PRIORITY | sort) \
         <(grep -oE '`[a-z0-9.-]+\.md`' .ytstack/backlog/PRIORITY.md | tr -d '`' | sort -u)
```

Empty output means the index covers the directory (checked at this reconcile: empty).
