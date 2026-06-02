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

## [0.1.7] — 2026-06-02

### Fixed

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
