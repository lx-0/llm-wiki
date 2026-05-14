# Features — Implementation Map

Living overview of every engine feature: what's documented, where it's implemented, how to trigger it, and where reality drifts from the docs. Keep this in sync whenever a feature lands, moves, or gets retired.

**Status legend:**

- 🟢 **live** — implemented, wired into the CLI / piggyback / hook path, exercised in tests or by the operator
- 🟡 **partial** — implementation exists but a piece is missing (consumer gone, CLI wrapper missing, doc references stale)
- 🔴 **broken** — documented as working but cannot be invoked the way the docs claim
- 🟠 **planned** — referenced as a near-future feature; no implementation yet
- ⚫ **removed** — formerly shipped, intentionally taken out; kept here as anti-drift anchor

> Cross-reference: every entry below should appear in at least `docs/PROCESS.md` (process description), `docs/cli.md` (CLI surface), and one of the high-level docs (`README.md` / `docs/concept.md`). A feature that lives only in one of those places is a documentation gap; flag it in the **Known gaps** column.

## Contents

- [Capture (Path A)](#capture-path-a) — session-end hooks, flush pipeline, daily/
- [Ingest (Path B)](#ingest-path-b) — Collectors + legacy scanners + drop boxes
- [Compilation & query](#compilation--query) — compile.py, query.py, lint.py
- [Side loops (post-compile)](#side-loops-post-compile) — curiosity, suggestions, claude-md-optimizer, wiki-review
- [Vault UX layer](#vault-ux-layer) — dashboard, MOCs, hard facts, agent tasks, pin
- [Lifecycle CLI](#lifecycle-cli) — setup, status, update, seed, config, hooks, skills
- [Known gaps & drift](#known-gaps--drift) — pinned reality-vs-docs checks

---

## Capture (Path A)

| Feature | Status | Code | Trigger | Docs | Known gaps |
|---|---|---|---|---|---|
| Session capture (start/end) | 🟢 | `hooks/session-start.py`, `hooks/session-end.py`, `hooks/_transcript.py`, `scripts/flush.py`, `scripts/core/flush_pipeline.py` | Claude Code / Codex / Gemini / Cursor session lifecycle | README "What you get", PROCESS §2, concept "Sensory buffer" | — |
| Pre-compact safety flush | 🟢 | `hooks/pre-compact.py` | Context-window compaction in Claude Code | PROCESS §2 | — |
| Daily log append (`daily/YYYY-MM-DD.md`) | 🟢 | `scripts/core/flush_pipeline.py:append_to_daily` | flush.py extraction success | PROCESS §2, concept "Episodic memory" | — |
| Failed-flush archival + retry | 🟢 | `scripts/core/flush_pipeline.py:archive_failure`, `scripts/retry-failed-flushes.py` | flush.py extraction failure (rate limit, SDK error) → archived to `.wiki/sessions/failed-flushes/`; piggyback retries later | PROCESS §2 piggyback table | — |
| Multi-agent hook install | 🟢 | `lib/agents.sh`, `lib/hooks.sh` | `wiki hooks install` | README "Multi-agent hooks", cli.md "Hooks & skills" | Four agents wired: claude / codex / gemini / cursor. PI (`pi`) and opencode are documented as NOT supported in `help_hooks`. |

## Ingest (Path B)

### Registry-discovered Collectors (`SPEC` + `@register` + `run()`)

| Collector | Status | Code | Output | Docs |
|---|---|---|---|---|
| `email` | 🟢 | `scripts/collectors/email_collector.py` + adapters in `scripts/adapters/mailbox/{thunderbird,gmail,allinkl,base}.py` | `raw/notes/email/<account>-<date>.md` | PROCESS §3 (scanners) |
| `jamie` | 🟢 | `scripts/collectors/jamie.py` | `raw/transcripts/jamie/<date>--<slug>--<id>.md` | PROCESS §3, README jamie line |

Dispatcher: `scripts/collectors/cli.py` (`wiki collect <name>` and `wiki collect --list`). Piggyback wiring: `flush.py:_build_piggyback_tasks` auto-discovers Collectors with `SPEC.piggyback_default=True`.

### Legacy CLI scanners (pending Collector port — backlog #1 in `architecture-deepening.md`)

| Scanner | Status | Code | Output |
|---|---|---|---|
| `calendar` | 🟢 | `scripts/collectors/scan_calendar.py:CalendarCollector` (Registry) + script-mode CLI | `raw/notes/calendar/calendar-overview-<date>.md` |
| `scan-browser` | 🟢 | `scripts/collectors/scan-browser.py` | `raw/notes/browser/` |
| `tabs` | 🟢 | `scripts/collectors/scan_tabs.py:TabsCollector` (Registry) + script-mode CLI | `raw/notes/browser/tab-groups-overview-<date>.md` |
| `scan-screenshots` | 🟢 | `scripts/collectors/scan-screenshots.py` | `~/Screenshots/<file>.md` (canonical) + `raw/notes/screenshots/thumb/<file>.png` + `raw/notes/screenshots/screenshots-<slug>.md` (batch report) |
| `scan-youtube` | 🟢 | `scripts/collectors/scan-youtube.py` | `raw/notes/youtube/<channel>--<title>--<vid>.md` |

`scan-youtube` is exposed via `wiki ingest-youtube`. `scan-screenshots` runs as piggyback (`piggybacks.scan_screenshots`). The others are operator-invoked via `uv run python scripts/collectors/scan-*.py` — no direct `wiki` subcommand yet.

### Drop-box / manual ingest

| Feature | Status | Code | Trigger | Known gaps |
|---|---|---|---|---|
| Inbox classifier | 🟢 | `scripts/process-inbox.py` | `wiki process-inbox` (+ `--no-compile` / `--dry-run` / `--model`); or `uv run python scripts/process-inbox.py` | — |
| HTML ingest (file or URL) | 🟢 | `scripts/ingest-html.py` | `wiki ingest-html PATH-OR-URL [--mode content\|visual\|both]`; also auto-invoked by `process-inbox.py` for HTML drops | — |
| Clippings sweep | 🟢 | `scripts/clippings_sweep.py` | Auto-triggered by `compile.py:start` when `features.clippings_sweep=true`; moves `<vault>/Clippings/*` → `raw/articles/` before compile | PROCESS §3, README — wired correctly via compile.py call site |

## Compilation & query

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Compile (raw + daily → knowledge) | 🟢 | `scripts/compile.py` | `wiki compile`, `wiki compile --all`, `wiki compile --file PATH`; auto-triggered by `flush.py` after `compile_after_hour` if daily/ changed | PROCESS §3, concept "Consolidation", README "Compile once, query fast" |
| Query (natural language → answer) | 🟢 | `scripts/query.py` | `wiki query "…"`, `wiki query --file-back "…"` (writes Q&A article) | PROCESS §5, concept "Retrieval" |
| Lint (8 structural + 1 LLM) | 🟢 | `scripts/lint.py` | `wiki lint` (full); `wiki lint --structural-only` (cheap, piggyback) | PROCESS §5, concept "Self-healing", cli.md |

Lint check inventory (in execution order in `lint.py`):

| Check | Severity | Auto-fixable | Function |
|---|---|---|---|
| broken_links | error | no | `check_broken_links` |
| orphan_pages | warning | no | `check_orphan_pages` |
| orphan_sources | warning | no | `check_orphan_sources` |
| stale_articles | warning | no | `check_stale_articles` |
| missing_backlinks | suggestion | yes | `check_missing_backlinks` |
| article_type | warning | yes | `check_article_type` |
| sparse_articles | suggestion | no | `check_sparse_articles` |
| facts_violations | warning | no | `check_facts_violations` |
| contradictions | warning | no (LLM) | `check_contradictions` (async, excluded by `--structural-only`) |

## Side loops (post-compile)

| Loop | Status | Code | Trigger | Known gaps |
|---|---|---|---|---|
| Curiosity loop — producer | 🟢 | `scripts/curiosity/producer.py:maybe_generate_curiosity_requests` (called from compile.py per file) | After each compile, Gemma4 via Ollama writes `raw/requests/request-{slug}-{date}.json` | Runs when `features.curiosity_loop=true` |
| Curiosity loop — consumer | 🟢 | `scripts/curiosity/cli.py`, `scripts/curiosity/backends/email.py` | `wiki curiosity --list / --run-oldest / --run <slug> / --run-all / --clear-done`; piggyback `piggybacks.curiosity_followup` (24h cooldown) runs `--run-oldest` automatically | Backend dispatches by request `type`. Today: `email-deep-scan` (full bodies via Mailbox-adapter scan_deep). Future types add as `curiosity/backends/<type>.py`. |
| Optimization suggestions — producer | 🟢 | `scripts/suggestions/producer.py:maybe_generate_suggestions` (called from compile.py for email sources) | Triggered when compile.py processes an email source | — |
| Optimization suggestions — executor | 🟢 | `scripts/suggestions/cli.py` | `wiki suggestions --list / --approve / --reject / --review / --dry-run` (or direct `uv run python scripts/suggestions/cli.py …`) | — |
| Optimization suggestions — IMAP backend | 🟢 | `scripts/suggestions/backends/imap.py` | Invoked by `suggestions/cli.py` for `imap-move` / `imap-tag` / `imap-set-flags` actions | Account credentials via `.claude/.env` |
| CLAUDE.md optimizer | 🟢 | `scripts/optimize-claude-md.py` | `uv run python scripts/optimize-claude-md.py`; piggyback `piggybacks.optimize_claude_md` (24h cooldown) | PROCESS §9 |
| Wiki review (per-article quality) | 🟢 | `scripts/review-wiki.py` | `wiki review-wiki`; piggyback `piggybacks.review_wiki` (168h / weekly) | PROCESS §6 |

## Vault UX layer

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Dashboard.md (Obsidian Homepage) | 🟢 | `templates/dashboard.md`, `lib/seed.sh:seed_vault_templates` | Seeded on install / `wiki seed` | PROCESS §11, README |
| Dashboard stats refresh (`_dashboard-stats.md`) | 🟢 | `scripts/dashboard/dashboard_stats.py` | Synchronous post-flush in `flush.py:refresh_dashboard_stats` + `wiki compile / lint / seed / correct` shell-wrapper helpers | PROCESS §11 |
| Dashboard lint refresh (`_dashboard-lint.md`) | 🟢 | `scripts/dashboard/dashboard_lint.py` | Synchronous post-flush in `flush.py:refresh_dashboard_lint`; same shell-wrapper helpers | PROCESS §11 |
| Agent-button auto-wiring | 🟢 | `scripts/dashboard/agent_buttons.py`, `lib/seed.sh:_merge_agent_shell_commands` + `_rewrite_dashboard_agent_buttons` | `wiki seed` discovers `prompts/agent_*.md` with `button:` block, merges shell-commands data.json, rewrites marker regions in dashboard.md | PROCESS §13, M004 |
| Daily-button injection | 🟢 | `scripts/dashboard/inject_daily_button.py` | `uv run python scripts/dashboard/inject_daily_button.py` | — |
| Maps of Content (MOCs) | 🟢 | `knowledge/MOCs/*.md`, templates in `templates/knowledge/MOCs/`, `scripts/pin.py` | `wiki seed` seeds `people.md` / `projects.md` / `concepts.md` stubs; operator adds wikilinks | PROCESS §11 MOC subsection |
| `wiki pin` (article → MOC section) | 🟢 | `scripts/pin.py` | `wiki pin <article> [--section "Name"] [--moc people] [--summary "X"]` | PROCESS §11 |
| Bases-browser (`knowledge.base`) | 🟢 | `templates/knowledge.base`, `lib/seed.sh:seed_vault_templates` | Seeded as additive template; Obsidian native (1.10+) | PROCESS §11 |
| History layer (`history.jsonl`) + P2 charts | 🟢 | `scripts/core/utils.py:append_history`, `read_history`; dashboard.md "📈 History" section | Auto-appended on compile / flush events | PROCESS §11 |

### Hard facts (corrections)

| Feature | Status | Code | Trigger |
|---|---|---|---|
| `wiki correct add / list / remove / edit / path` | 🟢 | `scripts/facts/correct.py` | `wiki correct <subcommand>` |
| `wiki correct apply <slug>` (agentic propagator) | 🟢 | `scripts/facts/correct_apply.py` | `wiki correct apply <slug> [--dry-run]` |
| Compile/query/lint integration | 🟢 | `prompts/compile_main.md`, `prompts/query_main.md`, `scripts/core/utils.py:read_hard_facts`, `scripts/lint.py:check_facts_violations` | Facts inject top-of-prompt at compile + query; lint greps `negation_terms` |

### Agent tasks

| Feature | Status | Code | Trigger | Docs |
|---|---|---|---|---|
| Generic agent runner | 🟢 | `scripts/agent_task.py`, spec parser `scripts/core/agent_spec.py` | `wiki agent <id>`, `wiki agent --list`, `wiki agent <id> --dry-run`, `wiki agent <id> --var key=value` | PROCESS §13, M004 |
| `summarize-day` task | 🟢 | `prompts/agent_summarize-day.md` | `wiki agent summarize-day --var date=YYYY-MM-DD` | M004-S02 |

Currently 1 agent task ships. Adding a new task = drop `prompts/agent_<id>.md` with frontmatter spec + optional `button:` block. No engine code change required.

## Lifecycle CLI

| Command | Status | Code | Notes |
|---|---|---|---|
| `wiki setup` | 🟢 | `wiki:cmd_setup`, `lib/config.sh:setup_wizard`, `lib/hooks.sh` | 5-question wizard + hook install |
| `wiki status` | 🟢 | `wiki:cmd_status` | Config summary + hook install table + Ollama probe |
| `wiki update` | 🟢 | `wiki:cmd_update`, `lib/skills.sh` | `git pull --ff-only` + skill sync; preserves `config.yaml` + `.venv/` |
| `wiki seed` / `wiki seed --force` | 🟢 | `wiki:cmd_seed`, `lib/seed.sh` | Additive template seed + drift detection |
| `wiki config` (get/set/keys/path/wizard/status) | 🟢 | `wiki:cmd_config`, `lib/config.sh`, `scripts/core/wiki_config.py` | Round-robin backup on every set |
| `wiki hooks` (install/uninstall/status) | 🟢 | `wiki:cmd_hooks`, `lib/hooks.sh`, `lib/agents.sh` | jq-merge into agent settings.json |
| `wiki skills` (install/uninstall/sync/status) | 🟢 | `wiki:cmd_skills`, `lib/skills.sh` | Symlink into `<vault>/.claude/skills/`, foreign entries preserved |
| `wiki gmail-auth <id>` | 🟢 | `wiki:cmd_gmail_auth`, `scripts/adapters/mailbox/gmail.py` | One-time OAuth bootstrap |
| `wiki version` | 🟢 | `wiki:cmd_version` | Git revision + tag + origin URL |

## Known gaps & drift

These are pinned reality-vs-docs checks. Each should either get fixed or get an explicit ADR explaining why the gap stays.

| # | Gap | Documented as | Actual state | Action |
|---|---|---|---|---|
| 1 | ~~Curiosity-loop consumer missing~~ | PROCESS §7, concept "Curiosity loop", README "Curiosity loop" all describe a producer→consumer cycle | **Closed 2026-05-13:** `scripts/curiosity/` subsystem shipped (Option B from backlog) — producer extracted from compile.py, `wiki curiosity` CLI consumer, `backends/email.py` dispatches `email-deep-scan` requests via the existing Mailbox adapters' `scan_deep`. Piggyback `curiosity_followup` runs `--run-oldest` every 24h. |
| 2 | ~~No `wiki process-inbox` subcommand~~ | PROCESS §1 documents Inbox Processing as a numbered process | **Closed 2026-05-13:** `wiki process-inbox` wrapper landed. |
| 3 | ~~No `wiki ingest-html` subcommand~~ | README "Path B" lists `ingest-html (file or URL)` as a substrate-source writer | **Closed 2026-05-13:** `wiki ingest-html` wrapper landed. |
| 4 | ~~No `wiki suggestions` subcommand~~ | PROCESS §8 documents the suggestion executor as part of the engine CLI surface | **Closed 2026-05-13:** `wiki suggestions` wrapper landed. |
| 5 | **`scan-*.py` legacy pattern still in `_LEGACY_PIGGYBACK_COMMANDS`** | README "Two-path ingest" says "remaining `scan-*.py` are scheduled for [Collector] migration" | Phase 2 underway. **2026-05-13:** `scan-tabs` migrated → `scan_tabs.py:TabsCollector`. **2026-05-14:** `scan-calendar` migrated → `scan_calendar.py:CalendarCollector`. Remaining: browser, screenshots, youtube. Status in `.ytstack/backlog/architecture-deepening.md` candidate #1 Phase 2. |
| 6 | **`origin: "scan-email/<id>"` in email Collector report frontmatter** | n/a (cosmetic) | `collectors/email_collector.py:111` still writes the old origin string. No engine reader; cosmetic only. | Flagged; intentionally left to avoid splitting report vintages |

## Maintenance protocol

When a feature lands:
1. Add or update the row in the matching section table.
2. Cross-reference: add it to `docs/PROCESS.md` (with a process-section if non-trivial), `docs/cli.md` (if it has a `wiki` subcommand), and one of README / concept.md (if it's user-visible).
3. If a config knob is involved, add it to `docs/config.md`.
4. If the feature *removes* something else, mark the removed row as ⚫ and link the supersede entry.

When a feature is retired:
1. Update its row to ⚫ removed with the commit SHA and a one-line reason.
2. Sweep all docs for stale references (`grep -rn '<feature>' docs/ README.md AGENTS.md`).
3. Add a DECISIONS.md entry if the retirement is non-obvious.

When the docs make a claim, verify the implementation exists before merging — that's the whole point of this file.
