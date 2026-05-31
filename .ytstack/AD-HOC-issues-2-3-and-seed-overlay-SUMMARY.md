# AD-HOC: GitHub issues #2 + #3 shipped, then a seed-robustness / config-overlay arc (2026-05-31)

## Trigger
Operator asked to triage open GitHub issues (#2 dream web-research, #3 entity
dedup), then implement both. Doing so surfaced a cascade of seeding gaps (a new
`EXA_API_KEY` env var wasn't discoverable, `wiki seed` couldn't add it; drift
reporting was noisy; agent-shell-commands merge silently failed; customisable
configs had no force-vs-drift escape), which turned into a sustained
seed-robustness arc culminating in a config-overlay subsystem. Versions 0.1.1 →
0.1.6.

## Shipped — features
- **#3 `wiki dedup`** (`scripts/dedup.py`, 18 tests) — interactive entity-dedup
  for STT-noise duplicates. $0 stdlib detection (difflib + German-aware phonetic
  key + shared `compiled_from` BOOST-ONLY, because daily-digest co-occurrence is
  not duplication), operator-confirmed merge (fold sections/aliases/sources,
  rewrite wikilinks B→A via `core.links`, backup+delete B, canonical-name
  negation fact). Verified live on lxw (4 candidates; dry-run merge). See
  `backlog/shipped/entity-dedup.md`.
- **#2 dream web-research** (`scripts/web_research.py` + `dream.py` post-pass,
  14 tests) — Exa-AI public-entity enrichment. NOT a compile producer — a dream
  POST-PASS (the producer registry is post-compile-shaped). Doubly gated,
  air-gapped from `raw/`, own 30d cooldown, fail-soft. Exa HTTP path verified
  LIVE on lxw (real call + real write to alex.md + idempotent upsert; the
  earlier "unverified" REGEL-#1 caveat is cleared). See
  `backlog/shipped/dream-web-research.md`.

## Shipped — seed robustness (0.1.2–0.1.6)
- **Targeted seed** `wiki seed <path> [--force|--check]` — act on one file.
- **`.env.example` additive per-var merge** — new engine vars (EXA_API_KEY) get
  appended with their doc-comment, operator file preserved (was keep-or-force).
- **JSON-order-aware drift** — `app.json`/`core-plugins.json` re-serialised by
  Obsidian no longer report as drift (canonical `jq -S` compare).
- **agent-shell-commands merge fix** — plugin stores `shell_commands` as an
  ARRAY of `{id,…}`; merge treated it as an object (`array+object` → jq error →
  silent "merge failed"). Now converts + merges by id. Later excluded from the
  overlay loop (it has its own additive merge) + made check-aware.
- **Config overlays** (the headline) — `graph.json`/`app.json`/plugin
  `data.json` derived as `template ⊕ overlay`; operator delta lives in an
  UNTRACKED `<vault>/.wiki/custom/<rel>`; `--force` re-derives non-destructively;
  `wiki seed --extract-custom <rel>` bootstraps from current drift. See
  DECISIONS 2026-05-31.
- **uv.lock sync** — lock recorded 0.1.1 while pyproject bumped through 0.1.6 →
  every `wiki update`'s `uv sync` dirtied the vault tree. Re-locked + added the
  "bump version → `uv lock` → commit lock" rule to the CHANGELOG convention.

## Incident (owned)
While checking the overlay on lxw I ran `wiki seed quickadd --force` on the
buggy 0.1.3 engine. jq's `*` replaces arrays wholesale, so a sparse overlay
array zeroed the QuickAdd choice names/ids (~330 fields). Recovered exactly via
`deepmerge(template, overlay)` (the overlay held the diff; the corrupted live
was backed up first), root-caused, and fixed in 0.1.4 (element-wise deepmerge).
Lesson → KNOWLEDGE 2026-05-31: never run a destructive `--force` of a brand-new
merge path against a live operator config before round-tripping it on the real
data shape (array-containing) in a fixture.

## Privacy note
Issues #2/#3 used a real person's name + company as examples; these were
propagated into code/docs/tests/commit-messages, then scrubbed to fictional
placeholders (working tree + the one offending commit message, via soft-reset
recommit — nothing leaked to the pushed history; verified).

## State
All shipped + pushed; lxw on 0.1.6, clean tree, both features live-verified.
Issues #2 + #3 CLOSED on GitHub. Only residual: `knowledge.base` drift =
operator's own sort-by-type-DESC view tweak (YAML, not overlay-managed) — leave
it; forcing gains nothing and loses the tweak.

## Open / deferred
- web-research Phase 2: LLM distillation into Company/LinkedIn/Known-for (v1 is
  a deterministic link-list block). Backlog candidate.
- Overlay system is JSON-only; YAML configs (`knowledge.base`) could get `yq`
  overlay support to stop showing as drift. Nice-to-have.
- dedup interactive merge (non-dry-run) still only unit-tested + dry-run-verified
  live; a real operator merge is the remaining live gap.
