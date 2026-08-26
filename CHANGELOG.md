# Changelog

All notable user-facing changes to the LLM-Wiki engine are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet cut tagged releases — changes land on `main` and reach
operator vaults via `wiki update`. The blow-by-blow engineering history lives in
git and in `.ytstack/` (DECISIONS.md, KNOWLEDGE.md, per-milestone SUMMARY files);
this file is the curated, capability-level view.

Because pushing to `main` *is* releasing (operators pull via `wiki update`), there
is no `[Unreleased]` bucket — when you ship an operator-visible change, add a new
dated `## [x.y.z] — YYYY-MM-DD` section at the top, bump `version` in
`pyproject.toml` to match, re-run `uv lock` and commit the `uv.lock` change in
the same commit (the lockfile records the project version, so skipping it makes
every operator's `wiki update` → `uv sync` regenerate `uv.lock` and dirty their
`.wiki/` tree), and group the entries (Added / Changed / Fixed / Removed). New
config keys must also be wired into `scripts/migrations/migrate_config_keys.py`
in the same commit.

## [0.5.1] — 2026-08-26

An adversarial re-audit of 0.5.0 — the reliability wave checking its own work.
Four of its changes were wrong or incomplete, and the audit that drove them had
one premise that did not survive contact with the operator's actual config.

### Fixed

- **`models.compile_model` was never a dead knob.** 0.5.0 read only the compile
  router, saw Haiku pinned on every row, and re-tiered the knob to Haiku. Five
  other surfaces read it with no pin of their own — including `wiki correct
  apply`, the agent that writes corrections into `knowledge/` — so the change
  silently downgraded them, and the migration rewrote any operator re-pin back
  on every `wiki update`. `compile_model` returns to Opus; the compile
  fall-through keeps its own knob. Affected configs are migrated back.
- **The bash-`[[ … ]]` guard reached only half its consumers.** It landed on
  the shared wikilink regex, but `lint`, the links audit, and the compile
  router go through a second, looser extractor that kept matching shell tests.
  There is one grammar now, and the broken-link check skips fenced code like
  every other link pass — 21 phantom errors gone from the live vault.
- **Seven config knobs reached no operator vault.** They sat in the migration's
  never-inject list on the premise that every config already carried them from
  its install-time copy; that copy happens once, so anything added later never
  arrives. Among them the threshold gating compile's long-context retry, whose
  on/off switch *was* visible. The never-inject classes are now stated in terms
  a reader can check, and are frozen against silent growth.
- **`wiki doctor`'s new piggyback check read the wrong state keys**, reporting
  twelve healthy tasks as never-run, and called a substrate dark after a few
  quiet hours. It walks the scheduler's own task list now, with a floor under
  the staleness threshold.
- **Retry-archive files with unrecognised names were stranded** — never retried
  and never reported. One real context had been invisible since July.

### Changed

- **`lint` no longer ships a hardcoded domain list.** `graph_view.domain_tags`
  is the source; vaults that predate the knob are seeded with the old built-in
  list so nothing changes for them, and the domain-tag checks stay quiet when
  no domains are configured rather than warning against an empty set.
- **The dollar counter is fully retired.** 0.5.0 stopped compile writing it
  while `wiki query` kept accumulating and the dashboard kept rendering it, so
  the "lifetime" figure drifted upward from queries alone. The field, its
  template line, the health line and the docs row are gone; per-run cost still
  prints. A vault's historical value is left untouched.

## [0.5.0] — 2026-08-26

The reliability wave (M031), driven by a full-state audit of the operator's
live vault. Three silent-failure classes are closed: session flushes that
died without a trace, `knowledge/index.md` drifting away from the corpus, and
piggyback/collector trouble nothing ever surfaced. The theme is that a failure
you cannot see is worse than one that shouts — every fix here either removes
the silence or makes `wiki doctor` say it out loud.

### Added

- **`wiki reindex`** — deterministic reconciliation of `knowledge/index.md`
  against the corpus (dedupe last-wins, drop dangling rows, append missing
  ones with first-paragraph summaries), preserving surrounding prose
  byte-for-byte. `--dry-run` reports without writing. It also runs
  automatically as a post-compile pass, replacing the LLM bookkeeping step
  that caused the drift in the first place.
- **`wiki doctor` reliability checks** — `piggyback-health` walks every task
  the scheduler would fire and reports a failed/timeout outcome (with its
  error), a run stuck past the runner's wall-clock cap, or a substrate that
  has gone dark; `index-drift` dry-runs the reconciler and offers `wiki
  reindex` as a one-key fix.
- **gmeet export dead-letter** — un-exportable Drive doc-ids (access revoked,
  document deleted) are parked in a per-account negative cache after
  `limits.gmeet_export_dead_letter_attempts` failures instead of being
  re-attempted on every run, with a re-probe after
  `limits.gmeet_export_dead_letter_reprobe_days` so restored access heals
  itself.

### Fixed

- **Session flushes died silently for eleven days.** The bundled CLI exited 1
  with empty stderr because the host's MCP-server tools were injected into
  every request and one of them ships a schema the API rejects. Every engine
  SDK call now passes `--strict-mcp-config` with no MCP servers. The 234
  contexts that had piled up in the retry archive were drained.
- **Archive files with non-conforming names were stranded forever** — they
  were neither retried nor reported. One real context had been invisible
  since July.
- **The compile fall-through route was a hardcoded model literal**, so no
  operator could retune it. It reads `models.compile_default_route_model` now.
  (An earlier attempt re-pointed it at `models.compile_model` and re-tiered
  that knob to Haiku on the theory that it was dead — see 0.5.1, which undoes
  it.)
- **Bash `[[ … ]]` test syntax parsed as a wikilink**, producing phantom
  broken-link errors, index junk rows, and stripped brackets in published
  articles.
- **A piggyback's stale `last_error` survived its next completed run**, so a
  day-old timeout was reported for a run that had just failed for an entirely
  different reason.
- **`wiki lint` crashed** on frontmatter tags that YAML parsed as integers
  (e.g. a bare year).

### Removed

- **The legacy dollar counter.** `state.json`'s `total_cost` is no longer
  accumulated — token accounting in `usage.json`/LEDGER has been the metering
  surface since 2026-05-23. (Completed in 0.5.1; this release only stopped the
  compile writer.)

## [0.4.0] — 2026-08-25

The remote-access arc (M030): `wiki publish` mirrors the vault into a managed
wiki on the operator's meinkontext (context-mcp) server — substrate and
distillate as ONE wiki, readable by every agent anywhere over MCP. The vault
stays the only source of truth; ~6.5k articles live after the first rollout.

### Added

- **`wiki publish`** — one-way, content-hash-idempotent mirror per the
  context-mcp producer contract. `--dry-run` (+`--json`) prints the full plan
  incl. per-corpus totals and the count of non-markdown files that have no
  contract channel; `--auth` runs the one-time browser OAuth consent (DCR
  public client, PKCE S256, `offline_access` → headless refresh-token flow,
  incl. forced mid-run refresh when the access JWT expires); `--piggyback` is
  the cadence mode (quiet no-op while `publish.enabled: false`).
- **`publish.*` config block** (`enabled`, `endpoint`, `wiki_slug`,
  `wiki_name`, `roots`) + `piggybacks.publish` (cooldown 6 h) so the mirror
  stays fresh after the operator's normal compile loop.
- **Multi-root corpora** (`publish.roots`): knowledge/ plus — per the ALLES
  decision — raw/, daily/, reports/, workspace/. Slugs are fixpoints of the
  server-side slugification (escalating disambiguation: parent → full path →
  path+hash; deterministic 120-char cap); wikilinks normalize to global
  slugs (unresolvable ones degrade to plain text); descriptions come from
  the article's index.md summary row. Deleting a file archives the article
  upstream; re-creating it restores it with continuing version history
  (live-proven).
- **docs/setup-publish.md** operator runbook + PROCESS.md §17.

### Changed

- `MEINKONTEXT_TOKEN` in `.claude/.env` is now an explicit override only
  (must be a USER token — org api-keys are read-only for the write tools);
  the OAuth token store at `.wiki/state/meinkontext-oauth.json` is the
  default auth path.

### Fixed

- **`core/config.py load()` silently ignored whole new config sections** —
  the hand-maintained merge list lacked new blocks, so operator YAML read
  back as engine defaults (`publish.enabled: true` came back `false`). Now
  merged + guarded by a derive-from-schema loader regression test; the
  parallel silent gap in `config_docs.py _SECTIONS` is closed too.
- Description length now capped in UTF-16 code units (the server measures JS
  `String.length`; emoji count double — two live rejects).
- Bounded 5xx/connection retry with backoff (the server redeploys on every
  merge; a mid-run 503 no longer aborts the batch) and per-article resume
  from the manifest after hard aborts.
- `httpx` was engine-wide undeclared in `pyproject.toml` — now explicit.

## [0.3.0] — 2026-07-22

The architecture-deepening arc: 14 refactor candidates in 4 waves (C01–C14),
consolidating the engine's copy-pasted plumbing into named seams. Mostly
internal — but the sweep surfaced and fixed a series of live operator-facing
bugs, listed under **Fixed**.

### Added

- **`wiki preprocess` + the Preprocessor seam.** The three in-vault intake
  normalizers (`inbox`, `html`, `clippings`) now share one Protocol + Registry
  (`scripts/preprocessors/`), like collectors and producers. `wiki preprocess
  --list` enumerates them; `wiki preprocess <name> [source]` runs one
  (`--dry-run` supported). The legacy entry points (`wiki process-inbox`,
  `wiki ingest-html`, compile's clippings sweep) are unchanged shims.
- **`wiki auth <service> <account-id>`** (gmail | gmeet | calendar) — one OAuth
  bootstrap front-door; the existing `wiki gmail-auth` / `wiki gmeet-auth` /
  `wiki calendar-auth <id>` remain as aliases. The account id is passed as an
  argument, no longer interpolated into a `python -c` source string.
- **`folder-index` is a first-class collector** — visible in `wiki collect
  --list`, runnable as `wiki collect folder-index` (syncs every `kind=local`
  watched-folders root). `wiki index` keeps the rich flags (single root-id,
  `--force`).
- **Machine-readable seams for every desktop-consumed surface:** `wiki collect
  --list --json`, `wiki triage list --json`, `wiki query --json`, and
  `wiki compile --progress-json` (structured `PROGRESS {"current","total"}`
  stdout lines, default off). The desktop app consumes these instead of
  scraping human log prose, so operator-facing wording is free to change again.

### Changed

- **`wiki help` now lists every command.** Nine commands that were dispatchable
  but invisible to `wiki help` and non-TTY callers (produce, triage, bridge,
  backfill, reconcile, health-trends, usage, study, analyze) are shown;
  `wiki compile --help` again documents `--max-files`. The catalog is
  table-driven (`scripts/cli.py`), so help, menu and dispatch can no longer
  drift apart.
- **`wiki collect --account <id>` is honored** — it restricts a collector run
  to a single account substrate (email, calendar, gmeet, jamie, health).
  Handing `--account` to a non-account collector now exits with a clear error
  instead of being silently ignored.
- **Silent failures now surface.** Every intentional exception-suppression in
  the engine goes through the new labeled `swallow()` seam (`core/errors.py`)
  or explicit log-and-continue — ~43 previously-silent sites (health probes,
  browser/tabs scans, mailbox decodes, OAuth refresh, piggyback spawn, usage
  exit-flush, dream history appends) now leave WARNING/DEBUG log lines instead
  of vanishing. No pipeline behavior changed; only visibility.
- **State writes are crash-safe and race-free.** All engine JSON state saves
  are atomic (tmp + rename), and `state.json` updates merge under a lock — a
  compile running for minutes can no longer wipe out query/lint counters
  written meanwhile, and a mid-write crash can no longer tear the ingested
  ledger (a torn ledger meant a full recompile).
- **Token accounting is correct-by-construction at every migrated Claude-SDK
  call site.** One shared harness (`run_sdk_query`) records cache-inclusive
  totals to the usage ledger (`wiki usage`) on every outcome — study runs,
  analyst passes, `wiki query` and agent tasks previously under-reported input
  by orders of magnitude under prompt caching, or recorded nothing at all.
  `wiki query` no longer prints a made-up dollar estimate; its lifetime-cost
  stat now accumulates the SDK-reported actual. Bundled-CLI hangs surface as
  `kind=timeout` with partial-spend accounting at every migrated site.
- **Dream failures are visible to monitoring.** Per-call timeouts and
  prompt-too-large now exit nonzero on every path (entity / sweep / piggyback),
  so an unattended dream that hangs-then-aborts records `failed:<rc>` in
  piggyback-state.json instead of a false `ok`. `wiki dream list-candidates`
  shows the insufficient-corpus `backoff` flag next to `cooldown`. (Sweep
  exit codes changed from the conflated 5 to per-kind 3/4/6.)
- **Config layer single-sourced.** Every knob's name/type/default lives in
  `scripts/core/config_schema.py`; migration values, `config.example.yaml`
  and the `docs/config.md` tables are derived from it and drift-tested
  (documented coverage grew ~55 → 186 keys). Config loading is type-safe (a
  value that doesn't fit the schema type → WARNING naming the key + engine
  default kept; a YAML parse error → loud "running on factory defaults"
  ERROR). Piggyback defaults have ONE source: the zombie `email_incremental`
  key is gone (`piggybacks.email` is the real key), `piggybacks.health` is
  visible, and the dead `max_per_run` subkeys on jamie/gmeet/calendar are
  pruned from operator vaults. Runtime cadence unchanged.
- **Lint sees `knowledge/MOCs/` and no longer counts engine-written
  `## Backlinks` footers as link edges** — the Orphans dashboard queue reports
  real orphans again (expect a one-time jump after updating; review the new
  batch once). Dashboard refresh is faster and safer: the structural lint
  checks run once per refresh over a single corpus read (shared between the
  stats callout and the lint queues), and the post-command refresh runs once
  through the fcntl-locked path (previously eight copy-pasted unlocked bash
  call sites; manual `wiki flush` refreshed twice).
- **Reports carry their scoring geometry.** Per-instrument report frontmatter
  now records the instrument's Likert scale, max total and concern-band
  declaration, so the meta-report reads geometry off the report instead of a
  hardcoded per-slug table (older reports stay readable — missing geometry is
  recovered from the engine definition). Adding a new instrument is a
  YAML-only operation again.
- **The desktop app talks to the engine through one seam.** Every `wiki`
  invocation goes through a single `runWiki()` runner with a per-call timeout
  (a hung health check can no longer wedge the app) and consistent error
  handling, and the GUI parses the new JSON surfaces instead of prose.

### Fixed

- **Inbox HTML drops ingest again.** Every `.html`/`.htm` file dropped into
  `inbox/` failed silently and was stranded there forever — the delegation
  pointed at `ROOT_DIR/scripts/ingest-html.py`, a path that exists in no
  deployed vault layout (and the test mocked the subprocess to success). It
  now ingests in-process; a failed ingest leaves the original in `inbox/`
  (retryable, no data loss).
- **Dream web-research fires on sweep + piggyback**, not only single-entity
  `wiki dream <slug>` — the doubly-gated Public-Profile enrichment was
  previously dead on every unattended run, the paths it was engineered for.
- **Concern flags fire for every live clinical instrument.** The insomnia
  (ISI), burnout (OLBI) and stress (PSS-10) screens on the default
  longitudinal-baseline study were structurally flag-blind and could never
  surface an elevated band; concern bands are now declared per-band in each
  instrument's cutoffs.yaml.
- **`wiki analyze --vault <path>` resolves the analyst agent's citations
  against the given vault** (it previously discovered studies under `--vault`
  but ran the agent against the engine root).
- **Triage records round-trip umlauts and quotes.** Summaries like
  `Müller sagt "hi"` no longer garble to json-escaped text in `wiki triage`,
  triage.html, the desktop Triage list, or on accept into `workspace/todo.md`;
  legacy escaped records on disk decode cleanly without migration. Fact stamps
  (`applied:`, `last_reconciled:`) now surgically line-replace their single
  key, so operator formatting in `knowledge/facts/` survives apply/reconcile.
- **`daily/<date>/sessions.md` writes go through the flock-protected
  chokepoint** — the session hook was the last writer bypassing the
  one-writer-per-(date,source) lock; a concurrent burst of SessionEnd /
  Codex per-turn flushes can no longer silently drop a session block. All
  sentinel-region splices (`<!-- x:begin/end -->`) now share one
  `core.markers` primitive — a stray or reversed end marker can no longer
  corrupt calendar day-rollups, blind the web-research cooldown stamp, or
  write garbled text back (the reversed-marker corruption class is fixed once
  for all sites).
- **Evening flush skips an unchanged daily file again** — the skip check had
  been silently broken by schema drift, so every flush unconditionally
  spawned compile.
- **Setup wizard no longer downgrades the compile model.** Pressing Enter on a
  default install wrote the retired claude-opus-4-7, which the next
  `wiki update` bumped back. `config.example.yaml` gained 9 missing keys and
  now matches every engine default exactly (test-enforced; fresh installs
  previously got `curiosity_followup` at a 24h cooldown instead of the
  engine's 6h/max-5 drain rate).
- **Interactive menu: the `t` (triage) quick-action shortcut works** (it was
  declared but did nothing), and nine previously-unreachable commands
  (produce, bridge, backfill, reconcile, health-trends, usage, study, analyze,
  dedup) are now browsable.
- **Pictures multi-inbox message** — under a multi-inbox
  `personal.picture_inbox`, the "no pictures processed" message named only the
  last-scanned inbox path; it now describes the whole configured scope.

### Removed

- **Three dead compile knobs** (`compile_force_long_context_types`,
  `compile_max_turns_long_context`, `compile_large_source_chars`). They fed a
  model/turn escalation ladder that could never fire — substrate routing pins
  the model and turn budget per row (Haiku by default), so only the first
  ladder tier was ever reachable. `wiki update` prunes them from operator
  vaults. The only remaining model escalation is the one-shot kind=unknown
  retry with `compile_large_source_model` (unchanged).
- **The `missing_backlinks` lint check + its dashboard queue.** Since M020 the
  backlinks pass materializes the reciprocal edge as a footer on every
  compile, so the check was vacuous — reciprocity is an engine invariant, not
  a lint finding.

## [0.2.2] — 2026-07-14

### Added

- **Codex sessions are now captured.** The session-capture hooks were installed
  for every agent (`.claude`/`.codex`/`.gemini`/`.cursor`) and fired, but the
  transcript reader parsed only the Claude Code JSONL schema — so every Codex
  session yielded 0 turns and was silently skipped (121 rollouts, months of
  usage, entirely dark; the health check stayed green because it verifies hooks
  are *wired*, not that capture *works*). `read_transcript` is now format-aware
  (`hooks/_transcript.py`): a Codex `{timestamp,type,payload}` rollout is parsed
  (clean user prose from `event_msg/user_message`, assistant from
  `response_item/message`, tools from `function_call`/`custom_tool_call`;
  reasoning + developer noise skipped), and an unresolvable hook
  `transcript_path` falls back to locating the rollout by session id under
  `$CODEX_HOME`.
- **`limits.dashboard_refresh_timeout_s`** (default 300) — the post-flush
  dashboard refresh budget is now a config knob (was a hardcoded 120 s, too
  tight for a growing vault under iCloud fs-stat variance).

### Changed

- **Session daily blocks are replace-in-place per session id.** Codex has no
  SessionEnd event — its `Stop` hook fires per turn — so a single session
  flushed many times; each fire now replaces the session's block in
  `daily/<date>/sessions.md` (sentinel-wrapped) instead of appending a
  duplicate. `scheduling.dedup_window_seconds` raised 60 → 900 to coalesce the
  per-turn re-distills. Benign for Claude (one flush per session).
- **Health: gmail on a filter-only account reports `info`, not `warning`.** An
  account whose reader is IMAP but whose filter is `gmail-api` now surfaces
  "email reading via IMAP is unaffected; only the suggestions label/move filter
  is skipped" instead of the misleading "the gmail collector will skip it".

### Fixed

- **compile: a transient SDK `is_error` no longer aborts a whole batch.** The
  `is_error` branch collapsed every non-`max_turns` result into an opaque
  `agent_error` that the retry ladder skips (gates on `unknown`) yet the
  consecutive-failure counter still counted — 3 transient CLI hiccups in a row
  aborted the run. It now routes through `classify_failure` (fast empty-stderr →
  `cli_crash`; slow no-signal → `unknown`, which the small-source skip path
  survives).
- **Ollama-unreachable log spam.** An offline home GPU flooded
  `compile-errors.log` with ~299 near-identical "not reachable" WARNING lines
  (one per compiled file per pass); a process-scoped warn-once helper now emits
  one WARNING per run, the rest at DEBUG. The screenshot collector's
  Ollama-unreachable message is likewise a WARNING now (was ERROR).

## [0.2.1] — 2026-06-13

### Changed

- **`personal.output_language` now also covers curiosity + dream output.** The
  knob (issue #4, shipped 0.1.9) previously only reached the 8 compile substrate
  prompts. It now also injects into the curiosity gap-detector
  (`compile_curiosity` + `compile_curiosity_folder`, via `curiosity/producer.py`)
  and the dream-cycle entity re-synthesizer (`dream_entity`, via `dream.py`), so
  a vault with `output_language: "de"` gets German gap-questions and German
  resynthesized entity pages too — not just German compiled articles. `"auto"`
  (default) stays byte-identical on every path. No new config key; no migration.

## [0.2.0] — 2026-06-13

### Changed

- **`wiki correct apply` is now non-destructive by default** (issue #5). The
  apply-agent had been wide-open (Bash + `acceptEdits` + 50 turns, no hook) and
  once **deleted 17 `knowledge/` articles** applying a single `negation` fact while
  reporting only 6. The new model is **agent proposes, engine disposes**:
  - **`negation` supersedes by default** — the matching article is annotated
    (`status: superseded` + `superseded_by:` + `outdated_since:` + a banner under
    the H1), its history kept. *Outdated is not false.* Deletion is the rare opt-in.
  - **The agent is sandboxed** like the reconcile loop: no Bash, a PreToolUse
    path-scope hook (writes confined to `knowledge/` minus `facts/`, `daily/`,
    `index.md`, the operations log), `permission_mode="default"`, a config-bounded
    turn count. It can no longer shell out or delete — it annotates via Write/Edit
    and proposes renames/deletions in a JSON block the engine executes.
  - **Deletion is opt-in + recoverable:** `--allow-delete` (per run) or a fact
    `disposition: delete` (per fact) opens the gate, reserved for factually-false
    content; deleted files move to `.trash/<ts>/` (never `rm`). A deletion-enabled
    run is **refused on a dirty / non-git tree** unless `--force` — a clean git
    tree is what makes `.trash` recovery trustworthy.
  - **Reporting is ground-truth:** the engine logs the real filesystem delta (git
    porcelain / mtime snapshot) and **warns** when more files vanished than were
    accounted for — never the agent's free-text summary again.
  - **`--dry-run` shows the blast radius** (candidate files + planned per-file
    action + the deletion-gate state) without spending; `wiki correct add` warns
    when a `negation_term` is over-broad.

### Added

- **First-class `supersession` fact status** — "was true, now outdated" (e.g. an
  order volume that grew 174k → 256k). Annotate-only: never delete-eligible, even
  with `--allow-delete`. Distinct from `negation` (possibly *false*). Lint no
  longer re-flags an article already annotated `superseded` by the fact.
- New knobs `limits.correct_apply_max_turns` (50) and
  `limits.correct_broad_term_threshold` (15).

## [0.1.9] — 2026-06-13

### Added

- **`personal.output_language`** (default `"auto"`) — pins the **output prose
  language** of compiled `knowledge/**` articles, surviving `wiki update`
  (issue #4). `"auto"` keeps today's behavior — write in the source material's
  language — and renders every compile substrate prompt byte-identically, so
  existing vaults are a no-op on update. Set to a language (`"de"`, `"German"`,
  `"fr"`, …) to force **all** compiled prose — article titles, body, summaries —
  into that language regardless of source, while keeping code, technical
  identifiers, proper names, and the canonical structural section headers
  (`## State`, `## Timeline`, …) verbatim so downstream parsing / dedup don't
  break. Injected via a `${output_language_instruction}` placeholder (new
  `prompts/compile_output_language.md`) at the single central compile render
  site, so it reaches all 8 substrate prompts (`compile_main`, `compile_default`,
  `compile_daily`, `compile_health`, `compile_calendar`, `compile_pictures`,
  `compile_screenshots`, `compile_memories`). Distinct from
  `personal.voice_transcribe_language` (input transcription vs. output prose).
  Curiosity + dream render on separate paths and are not yet covered.

## [0.1.8] — 2026-06-10

### Fixed

- **Curiosity email-deep-scans returned 0 messages on every request** (761/761
  on the reference vault since 2026-05-15, reports all `_No messages matched._`).
  `ThunderbirdMboxReader._resolve_folder_alias` checked only the folder *head*
  via `Path.exists()` across all mbox roots: a legacy POP root's bare `Inbox`
  file satisfied the canonical-`INBOX` probe (case-insensitively on APFS) and
  vetoed the `INBOX-N` alias resolution the 2026-05-16 fix introduced — silently,
  since a zero-folder match is not an error. The resolver now checks the **full
  Thunderbird path** (`head.sbd/…/leaf`) per root, **case-sensitively**
  (`os.listdir` compare), for the canonical name and each `-N` candidate.
  Recovery: re-run `scripts/migrations/cleanup_empty_deep_scans.py --apply`
  after `wiki update` — it deletes the empty reports and resets the affected
  requests to `pending`. Note: folders synced without offline bodies (`.msf`
  only, no mbox) still legitimately yield 0.
- **Deep-scans crashed on multipart messages with raw 8-bit
  `Content-Disposition` headers** (`AttributeError: 'Header' object has no
  attribute 'lower'`) — the email package's compat32 policy returns a `Header`
  object instead of `str` for undecodable header bytes. Now coerced via `str()`
  before matching; the affected scan survives instead of erroring the request.

## [0.1.7] — 2026-06-02

### Added

- **`features.dream_require_entity_substrate`** (default `true`) — skips the
  dream-entity SDK call for `$0` when the corpus carries zero entity-specific
  substrate (only date-pulled daily digests that don't mention the entity). Such
  a pass is a guaranteed `INSUFFICIENT_CORPUS` no-op that otherwise bills a full
  prompt-cache write (~$0.80/entity). Set `false` to force a digests-only attempt.
- **`scheduling.dream_insufficient_corpus_backoff_max_days`** (default `30`) —
  when a dream runs but the agent returns `INSUFFICIENT_CORPUS` (common on
  generic-noun slugs like `kontakte` whose mention-scan false-matches unrelated
  text), the entity is backed off the sweep with an exponential window
  (`dream_cooldown_days × 2^(consecutive_no_ops-1)`, capped here). A successful
  synthesis clears it; `0` disables; `wiki dream <slug>` always bypasses it.

### Fixed

- **Dream-cycle threw a false "SDK reported only N input tokens" warning on
  every healthy call.** The bundled CLI caches the prompt, so `usage.input_tokens`
  is only the tiny *uncached* delta (~12 for a 40 KB prompt) — the real input
  lands in `cache_creation_input_tokens` + `cache_read_input_tokens`. New
  `core.sdk_helpers.UsageTokens` / `extract_usage_tokens()` fold the cache fields
  into the true input; the warning now gates on cache-inclusive tokens AND ~$0
  cost (a genuine early-exit still surfaces). Token ledger + displayed `in:`
  counts for both compile and dream are now cache-accurate; the per-file /
  per-run runaway budgets deliberately stay on the uncached basis so `cache_read`
  (re-counted per turn) can't falsely trip them.
- **Dream-cycle hard-failed `PROMPT_TOO_LARGE` on high-file-count entities** (e.g.
  the ytstack project page at 482 KB). The corpus was bounded by file *count*,
  never by *chars*. It now trims the lowest-value Tier-2 (then oldest Tier-1
  recent) substrate to fit the budget — authored content + daily digests are
  preserved — and only hard-fails if that non-droppable core alone exceeds the cap.
- **Designed dream no-ops flooded the errors-only triage log.** A legit
  `INSUFFICIENT_CORPUS` no-op and an over-budget corpus trim are expected
  outcomes → now logged at INFO; a byte-identical page *without* the
  `INSUFFICIENT_CORPUS` sentinel (the silent-write-failure surface this check
  exists for) still warns.

- **`wiki compile` re-listed the same source files as "to compile" on every run,
  forever.** Deterministic skips — empty files, `compile_role: final-only` pages,
  and `compile_skip_substrate_types` members (e.g. `type: email-delta`) — were
  skipped without recording their content-hash in compile state, so `select_files`
  re-selected them every run. On a real vault this immortalised 34 email-delta
  rollup sources + 3 hand-curated final-only notes, perpetually inflating
  "Files to compile: N" with work that is intentionally never compiled (email
  deltas are already digested into `daily/` at collection time). These skips now
  record their hash and drop out of the candidate list until their body changes —
  matching the existing source-and-final and health-rollup skip behaviour.

## [0.1.6] — 2026-05-31

### Fixed

- **`wiki dedup merge B --into A --dry-run` errored** ("unrecognized arguments:
  --dry-run") because `--dry-run` was argparse-top-level-only, so it had to
  precede the `merge` subcommand. Operators naturally append it — now accepted
  in either position.

## [0.1.5] — 2026-05-31

### Fixed

- **`obsidian-shellcommands/data.json` falsely reported as "drifted — extract-custom"
  in `wiki seed --check`.** It has its own additive-merge-by-id (agent buttons),
  but the overlay routing double-handled it through `_seed_json_overlay`. It's now
  excluded from the overlay loop and its merge reports state correctly in check
  mode (read-only) — no misleading overlay hint.

## [0.1.4] — 2026-05-31

### Fixed

- **Config-overlay deep-merge corrupted arrays** (regression in 0.1.3). The
  overlay apply used jq's `*`, which merges objects but replaces arrays
  wholesale — so a sparse overlay array (only the operator's differing fields)
  obliterated the template's array, dropping every field that matched the
  template. `wiki seed <plugin/data.json> --force` could zero out e.g. QuickAdd
  choice names + ids. Now uses an element-wise recursive deep-merge. If you ran
  `--extract-custom` + `--force` on a plugin `data.json` under 0.1.3, the live
  file is recoverable as `deepmerge(template, .wiki/custom/<path>)` — the overlay
  still holds your diff.

## [0.1.3] — 2026-05-31

### Added

- **Config overlays — engine-owned base ⊕ operator-owned delta.** Customisable
  JSON configs (`graph.json`, `app.json`, `core-plugins.json`, plugin
  `data.json`) are now derived as `engine-template ⊕ overlay`: the engine owns
  the base (so new-feature keys flow in on `wiki update`), and the operator's
  customisations live in an **untracked** overlay at `<vault>/.wiki/custom/<path>`.
  You edit the overlay, never the live file — so `--force` re-derives
  **non-destructively** (your edits persist, the engine's new keys land). This
  resolves the force-vs-drift dilemma: previously customising a seeded config
  meant either `--force` (lose edits) or `keep` (never get new-feature settings).
- **`wiki seed --extract-custom <path>`** — bootstrap an overlay from a file's
  current drift (deep-diff of live vs engine template). Run it once to migrate an
  already-customised config into the overlay model; afterwards edit
  `.wiki/custom/<path>` and `wiki seed <path> --force` re-derives.

## [0.1.2] — 2026-05-31

Seeding robustness, surfaced while shipping web-research (#2).

### Added

- **`wiki seed <path> [--force|--check]`** — targeted single-file re-seed.
  Restricts the whole run to one vault-relative file, so a stale file (e.g. an
  `AGENTS.md` still pointing at the relocated `knowledge/log.md`) can be
  refreshed with `--force` **without** clobbering unrelated operator
  customisations (QuickAdd macros, graph palette, …). An unmatched path warns
  instead of silently doing nothing.
- **`EXA_API_KEY`** entry in the `.claude/.env.example` template (web-research, #2).

### Changed

- **`wiki seed` `.claude/.env.example` is now an additive per-var merge** — it
  appends only the stanzas for engine vars the operator is missing (with their
  doc-comment blocks), preserving their file, instead of the whole-file
  keep-or-`--force`. A newly introduced env-var becomes discoverable without a
  destructive overwrite.
- **Drift detection ignores JSON key order** — `.json` configs that differ only
  in key order (Obsidian re-serialises `app.json` / `core-plugins.json`) report
  *up-to-date* instead of *drifted*, removing false-positive noise.

### Fixed

- **`agent shell-commands merge failed` on every `wiki seed`** — the
  obsidian-shellcommands plugin stores `shell_commands` as an array of `{id,…}`,
  but the merge treated it as an object (`array + object` → jq error → silent
  failure + stale agent buttons). Now converts + merges by `id`, preserving the
  operator's own commands.

## [0.1.1] — 2026-05-31

### Added

- **`wiki dedup` — interactive entity deduplication** (issue #3). Finds and
  merges transcription-noise duplicate entity pages (`josefine-bartsch` vs
  `josephine-bartc`, `veltari` vs phantom `veltary`). Detection is deterministic and
  $0 — `difflib` fuzzy + a German-aware phonetic key + shared `compiled_from`
  (boost-only). Every merge is operator-confirmed: B's Timeline / Action Items /
  Open Threads + aliases + sources fold into A, every `[[wikilink]]` B→A is
  rewritten across `knowledge/`, B is backed up (`.bak.<ts>`) and deleted, and a
  canonical-name hard fact is recorded. Flags: `--suggest-only`, `--dry-run`,
  `--threshold`, and `wiki dedup merge B --into A`. Config:
  `limits.dedup_fuzzy_threshold` (default 0.85).
- **Dream web-research — public-entity enrichment via Exa AI** (issue #2). A
  post-pass to `wiki dream <slug>` that researches PUBLIC people (founders,
  execs, speakers) on the open web and writes a sentinel-managed
  `## Public Profile` block into the page. Doubly gated
  (`features.dream_web_research` + per-entity `web_research: true` / the
  `public-person` tag), air-gapped from `raw/`, with its own 30-day cooldown
  (`scheduling.web_research_cooldown_days`). Standalone forced refresh:
  `wiki dream web-research <slug> [--dry-run]`. Config keys:
  `features.dream_web_research`, `personal.exa_api_key` (or env `EXA_API_KEY`),
  `scheduling.web_research_cooldown_days`.
  _Note: the live Exa HTTP call is built to the `exa-search-api` skill's
  authoritative shape but is unverified against the live API (no key at build
  time); v1 writes a deterministic link-list block, with LLM distillation
  deferred to a documented Phase 2._

## [0.1.0] — 2026-05-31

The engine snapshot at the time this changelog was introduced. Selected
operator-visible capabilities shipped up to this point:

### Added

- **Substrate collectors** (11): email/IMAP, Google Meet, Jamie meetings, Google
  Calendar, Oura health, voice notes (text + `whisper.cpp` audio for
  m4a/wav/mp3), screenshots, pictures (with EXIF + Android-filename metadata),
  YouTube intake, quick-capture, and an rsync `wiki bridge` for
  sandbox-restricted intake folders.
- **Knowledge maintenance**: `wiki compile`, `wiki dream` entity re-synthesis
  (sampled-activation tiered corpus), `wiki lint`, `wiki links` (broken-wikilink
  report + approval-gated fixer), `wiki reconcile` (autonomous concept
  consistency), `wiki health-trends`, `wiki correct` hard facts, `wiki take`
  third-party beliefs, `wiki query`, `wiki pin` MOCs.
- **Operator surface**: interactive `wiki` home screen, `wiki doctor` health
  audit, `wiki config`, Obsidian dashboard, `use-llm-wiki` skill for cross-project
  access.
- **Knowledge schema**: areas bucket, author attribution, compile-role axis,
  optional `domain:` frontmatter, connection-quality gate, backlinks footer,
  relativized wikilinks.

### Fixed

- Route `type: transcript` sources to `compile_main` (closes #1).
- Reliability: bound Ollama half-open-socket hangs, per-piggyback wall-clock cap,
  `review-wiki` resilience; O(N²)→O(N) lint orphan-link counting.
- `wiki update` runs `uv sync` so `pyproject.toml` changes reach the vault venv.

[0.1.6]: https://github.com/lx-0/llm-wiki/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/lx-0/llm-wiki/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/lx-0/llm-wiki/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/lx-0/llm-wiki/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/lx-0/llm-wiki/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/lx-0/llm-wiki/compare/v0.1.0...v0.1.1
