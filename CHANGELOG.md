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
