# Archives — first-class cold state for knowledge/

Today `knowledge/` articles have two states: *exists* (full visibility everywhere — MOCs, dashboard, graph, query) or *deleted*. There is no graceful cold state for things that were valid, became stale, but stay worth keeping for grep/graph reach. Adopted from PARA's Archives idea (the only PARA tier that maps cleanly onto lxw's entity-typed knowledge model). See `lx-vault-merge.md` for the audit that surfaced this.

## The pattern

Frontmatter flag on any `knowledge/**/*.md`:

```yaml
---
title: "Screenshot intake architecture"
type: concept
archived: true
archived_at: 2026-04-30
archived_reason: "shipped; reference only"
---
```

Behavior:
- **Default views hide archived**: `wiki query`, dashboard "Recent Concepts" / "Open Threads" / Action Items, MOC auto-includes, "Stale Articles" checks
- **Always reachable**: grep, Obsidian Search, graph view (optionally dimmed), wikilinks resolve normally
- **Compile-loop skips re-compile** by default — they don't drift because they don't get touched
- **`wiki query --include-archived`** as escape hatch

## Why it matters now

- lxw has been live since Feb 2026. Real cold-knowledge accumulates: shipped-feature concepts (`screenshot-intake`, `youtube-intake`), evaluated-and-rejected ideas, historical project pages whose State is finalized. Today they compete equally for dashboard real-estate with active items.
- Memory contains explicit examples (`project_screenshot_intake`, `project_youtube_intake`) where the article exists, is correct, but is reference-only — no further compile-passes will improve it.
- PARA's strongest claim — and the one Forte stands by hardest — is "Archives is the dump that keeps stuff retrievable without polluting active view". The audit of `lx/` (114 files, PARA-structured) confirmed this is the one PARA idea worth lifting. Everything else (Projects/Areas/Resources hierarchy, emoji folders) is rejected.
- Lower-cost than alternatives considered: separate `knowledge/archives/` folder (breaks wikilinks on archive transition); per-article `status: archived` enum (over-engineered, only need binary).

## Open design questions

- **Flag or folder?** Frontmatter flag wins on no-link-breakage. Folder loses because moving a file rewrites all `[[wikilink]]`s pointing to it. Recommend flag.
- **Does `archived: true` exclude from `compiled_from` lookups?** Probably not — provenance trails should resolve regardless. Only *active surfaces* hide.
- **Auto-archive heuristic?** Optional second iteration: if a `concept`/`project` has had zero substrate-source touches in N days AND is referenced only by already-archived pages, propose archiving via `wiki suggest`. Defer; manual flag is enough for v1.
- **Graph view treatment** — Extended Graph plugin: dim archived nodes (50% opacity) or hide-by-default with toggle? Operator preference; both cheap to implement via tag-based color rules (memory: `project_graph_view_multichannel`).
- **`wiki correct` interaction** — should `wiki correct` flag inconsistent archived/un-archived states (e.g. archived concept linked heavily from active pages = suspect)? Nice-to-have.

## Touchpoints

- `scripts/core/frontmatter.py` (or wherever schema validation lives) — add `archived: bool`, `archived_at: date?`, `archived_reason: str?` as recognized optional keys
- `scripts/dashboard/*` — filter by `archived != true` in all aggregation queries
- `scripts/facts/moc.py` (or equivalent MOC generator) — exclude archived from auto-includes; optionally keep manual `[[...]]` references
- `scripts/lint.py` — check `archived_at` is ISO-date if present; warn if `archived: true` but no `archived_at`
- `scripts/cli.py` `wiki query` — `--include-archived` flag, default false
- `scripts/compile.py` — skip re-compile if `archived: true` in current frontmatter (one-line guard near the top of per-file loop)
- `scripts/core/config.py` + `config.example.yaml` — `archives_hidden_by_default: bool = true` (must extend `migrations/migrate_config_keys.py` same-commit per project hard-rule)
- `templates/.obsidian/graph.json` — optional: archived-tag color rule
- `AGENTS.md` — document the flag

## Lift estimate

- Schema + lint + config + migration: 0.5 day
- Dashboard + MOC filtering: 0.5 day
- `wiki query` flag: 0.25 day
- compile.py skip-guard: 0.25 day
- Graph view dim rule: 0.25 day
- Testing on real corpus (find ~20 archive candidates, flag them, verify they disappear from active surfaces): 0.25 day

**~2 days end-to-end.**

## Risks

1. **Operator forgets to set `archived_at`** — lint warns, doesn't block. Cosmetic risk.
2. **Wikilink to archived page in active prose looks broken-feeling** — operator sees a link, follows it, page is "archived" — confusing? Mitigation: Obsidian-side CSS dims archived-page rendering with a banner ("archived 2026-04-30 — reference only").
3. **Auto-archive heuristic over-fires** (if implemented) — defer it; manual-only v1 has no auto-fire risk.
4. **Compile.py skip introduces drift** — if substrate referenced by an archived page changes, the archived page no longer reflects current substrate. Acceptable: archived = frozen, that's the point. Operator un-archives if they want a fresh compile.

## Ripens when

- Now. Real cold-knowledge already exists in lxw — every shipped-feature concept page is a candidate. Independent of `lx-vault-merge.md` (which surfaced the need but doesn't gate it).

## Status

**Subsumed by `compile-role-axis.md`** (2026-05-16). That backlog file proposes a 3-value enum `compile_role: source-only | source-and-final | final-only` that covers archives-flag's binary case as `compile_role: final-only` plus the additional `source-and-final` case for long-form deliberate writing. Recommendation: ship compile-role-axis instead; archives-flag-as-separate-feature has been retired.

File kept as historical artifact / decision-context (the simpler 80% framing was considered first, then absorbed into the more general axis after operator's own 2026-05-02 vault-architecture plan surfaced the long-form gap).
