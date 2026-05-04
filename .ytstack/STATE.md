---
project: llm-wiki
slug: llm-wiki
last_updated: 2026-05-04T09:00:00Z
current_milestone: M004
active_slice: none
active_task: none
---

# State

**Status:** M002 **done** (2026-05-02; 25 pytest tests green; commits `15b4916` S01, `14bf844` S02, `4e52520` S03, `b884bf1` finalize). Reader/Filter adapter seam landed for Thunderbird-mbox, All-Inkl-Procmail, and Gmail-API; legacy `scripts/scan-email.py` + `scripts/thunderbird-rules.py` deleted; `wiki_config.py` enforces nested `reader:`/`filter:` schema; round-robin config backup wired into every `wiki config set`. **Live Gmail smoke deferred** as operator-side action (drop `client_secret.json` → `wiki gmail-auth <id>` → `wiki collect email --account <id>`) — does not block M003.

**Doc restructure (2026-05-02 PM, commits `22900dc` + `59a5175`):** README went 460 → 311 lines via 9-repo audit (basic-memory, mem0, ollama, simonw/llm, nanoGPT, OpenHands, fabric, claude-memory-compiler, karpathy/nanoGPT) plus consistency pass against `.ytstack/`. Auxiliary docs created: `docs/cli.md` (CLI reference), `docs/engine-layout.md` (engine internals), `docs/vault-tour.png` (Obsidian-mockup infographic via lo-fi-wireframing-kit). All linked docs got TOCs. Two backfill DECISIONS.md entries: naming vocabulary lock + `.venv/` location hard-rule. README "8 collectors" claim corrected to "9 substrate sources" (only `scan-email` is on the formal Collector pattern post-M002). Deferred follow-ups in `backlog/readme-polish.md`.

**Status:** M003 in progress (1/6 slices done — S01 grew from 5 → 8 tasks during execution). S01 closed with rich interactive Dashboard: capture buttons (Meta Bind + QuickAdd), live engine-status callout with pending-list, 5 graphical charts (Source-type doughnut, Top-15 tags bar, Article freshness, Inbound-link histogram, Daily activity heatmap), Inbox/Pending-review/Tasks triage, Run-buttons (compile / lint / refresh-stats via Shell commands plugin), Orphan list. Theme-aware Chart.js colors via Obsidian CSS vars, responsive grid via cssclasses + CSS snippet.

**Wiki CLI massive expansion** — gained `compile / flush / lint / query / review-wiki / seed / correct` subcommands; was lifecycle-only before. `_run_script` + `_refresh_dashboard_stats` helpers dedupe wrappers.

**Hard-facts subsystem (user-led, parallel to S01)** — new `knowledge/facts/<slug>.md` with `type: fact` frontmatter. `wiki correct add/list/remove/edit/path` CLI in `scripts/correct.py`. `prompts/compile_main.md` injects facts as authoritative override over source material. Lint check_article_type knows about `facts/ → fact`. Migration script + tests adjusted accordingly.

**Hard-facts trust + sources extension (2026-05-03, commit `4ec926e`):** every fact now carries `trust:` (`confirmed | asserted | provisional`, default `asserted`) and `sources:` (≥1, REQUIRED at creation — `wiki correct add` exits 2 without `--source`). User IS a valid source via sentinels like `user:2026-05-03`. `read_hard_facts()` sorts injected facts by trust tier DESC then `updated` DESC; each renders with `[trust: X]` header + `> Sources: ...` line. Compile + query prompts gained a conflict-resolution paragraph (higher tier wins; tie → newer; all tiers still override raw). Two legacy facts in lx-0 vault backfilled to `trust: asserted` + `sources: [user:2026-05-02]`. 9 new pytest cases, full suite 79/79. DECISIONS.md entry added. See PROCESS.md §13 + AGENTS.example.md schema for full schema.

**Root-cause fixes that landed:**
- `compile_main.md` now sets `type:` per folder; `AGENTS.example.md` documents knowledge/ frontmatter schema; lint flags missing_type / type_mismatch (auto-fixable); `scripts/migrate_add_type.py` backfills legacy articles. Replaces earlier symptom-fix where dashboard chart fell back to folder name.
- `lint.py:check_stale_articles` defensive isinstance handling for `state.ingested[rel]` (string in current schema, dict in legacy). Per-check try/except in main loop so one crash doesn't kill the run.
- `templates/.obsidian/plugins/dataview/data.json` seeds `enableDataviewJs: true` so charts render without manual toggle.
- Meta Bind buttons: `cssclasses: [wiki-dashboard]` instead of inline `<div>` wrappers — Meta Bind post-processor doesn't run inside raw-HTML context.

**`wiki seed` command** — additive in-place re-application of templates to installed vaults (community-plugins.json merged via jq, never destructive). `wiki seed --force` overwrites existing files. `lib/seed.sh` is the shared logic, used by both `install.sh` and the CLI.

**Plugins shipped** (8 community + Obsidian-builtin): dataview, homepage, obsidian-charts, heatmap-calendar, obsidian-meta-bind-plugin, obsidian-tasks-plugin, obsidian-shellcommands, quickadd, plus existing obsidian-excalidraw-plugin. Plus CSS snippet `wiki-dashboard.css`.

**Tests:** 37 pytest tests green (was 25 pre-M003).

**M003 — Human Vault UX:** Dashboard.md (auto-opens via homepage plugin) with engine-status callout, lint-triage queues, P1+P2 charts (5+3, single-snapshot + time-series), MOC layer (≥3 manually curated), state.history.jsonl append-only history, Bases knowledge browser. Six slices S01–S06. Source design in `backlog/vault-dashboard.md`; locked decisions + exit criteria in `M003-CONTEXT.md`.

Carried-forward candidates from M002 (deferred to M004+): Collector-rollout to other substrates, multi-vault ingest, source-onboarding cadence.

**Hotfix post-M004 (2026-05-03, commits `618b1dd` + `5900496`):** `compile.py` now writes a persistent file-log (`<wiki>/logs/compile.log`, INFO+, mirrors stderr) plus a triage-only sibling (`compile-errors.log`, WARNING+). Same run also hardened `maybe_generate_curiosity_requests`: Ollama (`gemma4:e4b`) was observed returning `gaps` as a list of strings despite item-level `type: object` in the schema, killing the curiosity pass with `AttributeError`. Now non-dict items are dropped with a logged sample. Lesson recorded in `.ytstack/KNOWLEDGE.md` "Ollama structured output" section. Docs: `docs/PROCESS.md` §8 Edge Cases + `docs/engine-layout.md` log-file inventory.

**YouTube intake landed (2026-05-03, post-M004 feature, commits `aafe2a8` `9ca7c43` `825ea94` `5bb0c0e`):** New `scripts/scan-youtube.py` collector and `wiki ingest-youtube` CLI subcommand. Tier 0 (yt-dlp metadata) + Tier 1 (transcript via `youtube-transcript-api` with `yt-dlp .json3` fallback) + Tier 2 (top comments via yt-dlp) + **Tier 3-local** (ffmpeg chapter-aligned / fixed-interval frame sampling → gemma4:e4b @ kcma per-frame vision → gemma4 text-mode aggregation using transcript + frame summaries). Single `.md` sidecar per video, no parallel JSON. Playlist URL normalization (`watch?v=…&list=L` → `playlist?list=L`), inbox parser (bare URLs / markdown links / shortlinks / inline `tier: N` directives), skip-existing dedup by `video_id`. End-to-end verified on a 20min Morpheus tutorial with captions disabled — 11/20 informative frames, 6 key concepts + 11 visual artifacts + 2 code snippets in ~14min @ $0. CONFIG-driven per `AGENTS.md` framework standard: `limits.youtube_{max_frames,max_duration_s,frame_resize_width,vision_timeout_s,aggregate_timeout_s}` + `piggybacks.scan_youtube`; `models.vision_model` reused for vision + aggregate. Lxw vault config patched to add `piggybacks.scan_youtube`. Docs updated: AGENTS.md, README.md, docs/{cli,concept,PROCESS}.md, architecture.excalidraw + overview.excalidraw (substrate count 9 → 10). Two new DECISIONS entries (intake design + lift-hardcoded-into-CONFIG framework rule), three new KNOWLEDGE.md learnings (cloud-cost-reality, JSON-overdesign, dev-vs-prod path resolution). Tier 3-cloud (Gemini Flash-Lite with cost-protection guardrails lifted from clawrag's pain-driven design), curiosity-loop search/upgrade requests, generic curiosity-dashboard surface deferred to backlog.

**Hotfix 2026-05-04 (commit `25bcab8`):** SDK error-handling stabilized engine-wide. Audit of `lxw/.wiki/logs/` showed ~190 `Command failed with exit code 1 — Check stderr output for details` entries with no further context, and `compile.py:main()` mis-attributing 1.9 s / 2.7 s / 3.3 s fast-fail bursts to "rate-limited (5 h Opus window)". New `scripts/sdk_helpers.py` provides `StderrCapture` / `classify_failure` / `log_sdk_failure` / `is_fatal`; wired into all 8 SDK call sites (compile×2, flush, correct_apply, agent_task, lint, optimize-claude-md, query). Compile loop now classifies each failure (`rate_limit` / `auth` / `model` / `network` / `oom` / `cli_crash` / `unknown`); aborts fail-fast on auth/model errors, distinct messages per kind, outcome banner uses `ABORTED (<kind>)` for grep-friendly post-mortems. Same commit fixes the dashboard-refresh storm (103 `subprocess.TimeoutExpired` records on 2026-05-03 around 19:02): non-blocking fcntl lock on `state/dashboard-refresh.lock` so concurrent SessionEnd hooks no longer all spawn their own refreshers, plus 30 s → 120 s timeout and structured `_run_dashboard_script` logging that distinguishes TIMEOUT / spawn-failed / non-zero exit. Also fixed `docs/cli.md` cheat-sheet (commit `57d509e`) — was missing 11 subcommands (compile, flush, lint, query, review-wiki, skills×4, collect×2, gmail-auth, seed, agent×4, version) and several flags. Two new DECISIONS entries.

**M004 done (2026-05-02):** Agent-Task framework shipped. `scripts/agent_spec.py` (parser, 8 validation cases), `scripts/agent_task.py` (SDK runner with `--list / --dry-run / --var`), `scripts/agent_buttons.py` (discovery + dashboard region-rewrite), `wiki agent <id>` CLI. First concrete task: `prompts/agent_summarize-day.md` (Haiku, Read/Edit/Write, primary button). Auto-wiring via `wiki seed`: jq-merge into shell-commands data.json + marker-based region replace in dashboard.md. 20 pytest tests green (17 spec + 3 summarize-day smoke). PROCESS.md §14 + KNOWLEDGE.md learning + DECISIONS.md two entries (framework + region-marker pattern). Live vault patched, button visible in Run row after reload.

## Next action

M004 closed + YouTube intake landed as a post-M004 feature. Three paths:
- **Use it / harden** — drop URLs into `lxw/inbox/youtube.md`, run `wiki ingest-youtube --inbox <path>` from kcma piggyback. After ~10 real videos, decide if `qwen2.5-vl:7b` upgrade is worth pulling for stronger Code-OCR.
- **Tier 3-cloud** — implement Gemini Flash-Lite path with all guardrails from `youtube-intake.md` (hardcoded model, blob cache, pre-run estimate, `--allow-cloud`, budget cap). Worth doing once a video clearly needs visual fidelity local-vision can't deliver.
- **Curiosity-loop integration** — search/upgrade requests + generic dashboard-surface (`curiosity-dashboard.md`). Triggers when ≥5 requests/week from compile-loop justify the surface.
- **Reassess roadmap (M005?)** — does the agent-task catalogue need more tasks now (review-mocs, weekly-digest, extract-todos)?

## Open decisions

- **Multi-vault ingest** — see Next action above. Carried forward to M003 scoping.
- **Source-onboarding cadence** — see Next action above. Carried forward.

## Open decisions

- **Multi-vault ingest** — does the engine index multiple Obsidian vaults at once, or merge-then-ingest? Surfaced in the pitch as the project's own raison-d'être recursing into its own setup. Backlog-level question, surfaces during milestone scoping.
- **Source-onboarding cadence** — onboard older substrates (dormant vaults, exports, files from past systems) manually now, or wait for collectors + ingestion tooling to automate the long tail? Trade-off: incomplete map vs. noisy ingest. Milestone-scope decision deferred.

## Recent summaries

(Latest 3 T##-SUMMARY.md entries will appear here once tasks complete.)
