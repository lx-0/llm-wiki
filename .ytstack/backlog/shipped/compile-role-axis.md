# compile_role — generic axis for how compile treats a file

Generalizes `archives-flag.md` (binary archived-or-not) into a 3-value axis describing how compile.py should treat any `.md` file in the vault. Surfaces a real architectural gap: lxw today has no clean home for **deliberate long-form human writing** (strategy essays, manifestos, opinion docs). PARA had `🌈 Company/Areas/Portfolio/Strategy.md` for exactly this; lxw's `raw/notes/` is append-only substrate, `knowledge/` is engine-owned, neither fits. Surfaced during analysis of `imported/lx/plan/vault/lx-lxw-merge.md` (operator's own pre-merge plan from 2026-05-02).

## The axis

Single frontmatter key `compile_role`, three values:

| Value | Where it lives | Compile treats it as | Example |
|---|---|---|---|
| `source-only` (default) | `raw/`, `daily/` | substrate → distill into knowledge/ articles | a meeting transcript, an article, a daily session log |
| `source-and-final` | `raw/notes/longform/` (or anywhere) | indexed (mentions extracted, backlinks built) but NOT distilled into a separate knowledge/ page; the page IS the final form | strategy workdoc, mission/vision/values, deep-thoughts essay |
| `final-only` | `knowledge/**/*.md` | engine-skip; hand-curated; reachable via grep/graph/search; hidden from MOC auto-includes and dashboard active surfaces | shipped-feature concept, archived project page, hand-written reference doc |

Default-by-location: omitting `compile_role` infers from path (raw/* → source-only, knowledge/* → engine-owned-as-today). Explicit value overrides.

## Why it matters now

- **Real architectural gap.** Strategy-thinking is a recurring human writing mode. Today it has no home in lxw — would push back to Apple Notes / Google Docs / scratch files (regression).
- **Absorbs `archives-flag.md`.** That backlog file's "archived: true on knowledge/ pages" is exactly `compile_role: final-only` under this axis. Shipping compile-role makes archives-flag a special case, not a separate feature.
- **Unblocks Phase 2 of lx-vault-merge.** Many lx imports (`yesterday-strategy-workdoc.md`, `Das Agentische Manifest`, `agi-assessment-2026-q1.md`) are exactly long-form essays that need `source-and-final`. Without this axis, they don't have a destination.
- **Cheap incremental extension.** Engine already has the concepts (compile skip, dashboard filtering, MOC inclusion); this consolidates them under one schema knob instead of accumulating ad-hoc flags.

## Coexistence with archives-flag.md

Two paths:

- **(A) compile-role-axis absorbs archives-flag** — ship compile-role-axis as M007, retire `archives-flag.md` backlog file. Operators use `compile_role: final-only` to archive.
- **(B) Ship both as parallel features** — archives-flag is 80%-cheap-version, compile-role is generic 100%-version, ship archives-flag first because it's simpler. Risk: schema drift if compile-role lands later with different semantics.

**Recommend (A).** Schema migrations are easier when there's only one mental model; "two ways to mark a page as engine-skip" is a confusion-trap. Backlog cleanup: mark `archives-flag.md` as "subsumed by compile-role-axis" on this file's ship.

## Open design questions

- **Default inference vs explicit-required?** Default-by-location is more ergonomic but creates surprise when an operator moves a file (raw/ → knowledge/ silently flips compile_role). Counter: explicit-required is verbose for the 90% case. Lean toward default-by-location with lint warning on cross-location moves without explicit override.
- **`source-and-final` indexing semantics** — what exactly does "indexed but not distilled" mean? Concrete: compile extracts `[[wikilinks]]`, surfaces in `knowledge/index.md` with its own pathname, contributes to `knowledge/connections/` candidates, but does NOT produce a `knowledge/concepts/<title>.md`. Probably right. Edge: does `wiki query` treat it as a knowledge source or a raw source? Probably knowledge-equivalent.
- **MOC behavior for `source-and-final`?** Should longform essays appear in MOC auto-includes? Probably yes — they're deliberate writing that should be discoverable. Distinct from `final-only` archived items which hide.
- **`final-only` in raw/?** Could an operator pin a raw/ file as "don't recompile, leave alone"? Edge case, defer.
- **Per-section roles** (some sections of a page are compile-source, others are final)? Over-engineering. Single-role per file.
- **Lifecycle transitions** (a longform essay solidifies into a final reference; an archived concept un-archives to be re-compiled) — explicit operator edit of frontmatter. No magic.

## Touchpoints

- `scripts/core/frontmatter.py` (or schema location) — add `compile_role: enum[source-only, source-and-final, final-only]` with default-by-location inference
- `scripts/core/config.py` + `config.example.yaml` — `compile_role_default_by_location: bool = true` (must extend `migrations/migrate_config_keys.py` same-commit per project hard-rule)
- `scripts/compile.py` — branch at per-file top: `source-only` → distill as today; `source-and-final` → index without producing distilled output; `final-only` → skip entirely
- `scripts/dashboard/*` — filter `final-only` from active surfaces (replaces archives-flag logic)
- `scripts/facts/moc.py` — include `source-and-final`, exclude `final-only` from auto-includes
- `scripts/lint.py` — validate enum; warn on cross-location moves without explicit override; warn on `source-and-final` without `last_edited` frontmatter (drift detection)
- `scripts/cli.py` — `wiki query --compile-role <value>` filter; `wiki query --include-final-only` flag
- `prompts/compile_main.md` — type-conditional rule: source-and-final pages get reference-indexed-only treatment in the index pass
- `templates/.obsidian/graph.json` — color-channel for compile_role (alongside type)
- `AGENTS.md` — document the axis

## Lift estimate

- Schema + lint + config + migration: 0.5 day
- compile.py branching (3 paths): 1 day
- Dashboard + MOC + query filter: 0.5 day
- Default-by-location inference: 0.5 day
- Migration of existing archive candidates (replaces archives-flag manual flagging): 0.5 day
- Testing on real corpus + 1 longform candidate: 0.5 day

**~3.5 days end-to-end.** Bigger than archives-flag (~2 days) but ships strictly more.

## Risks

1. **Schema-axis premature** — committing to a 3-value enum before second use case exists (longform) is justifiable; before third use case it's speculative. Mitigation: enum is extensible, not closed; future values (`draft`, `redacted`, …) compose cleanly.
2. **Default-by-location surprise** — operator moves file, compile_role flips silently, distillation/skip-behavior changes. Mitigation: lint warns; explicit override always wins.
3. **Compile prompt complexity** — adding "indexed-but-not-distilled" treatment to compile.py adds a third execution path. Mitigation: keep `source-and-final` minimal — just record in index, no LLM call. Cheapest possible third path.
4. **Engine vs operator overwrite races** — operator edits a `source-and-final` page mid-compile. Mitigation: same as today for raw/ edits — compile is operator-triggered or piggyback, no live file-watching.
5. **Migration tooling for archives-flag candidates** — if archives-flag never ships separately, no migration needed. If both ship, need a one-time `archived: true` → `compile_role: final-only` rewrite. Trivial sed-pass.

## Ripens when

- Now. Concrete demand from `lx-vault-merge.md` Phase 2 (operator strategy docs need `source-and-final` slot). Also independent demand from cold knowledge accumulating in `knowledge/`.
- Should ship **before** lx-vault-merge Phase 2 (along with `areas-bucket.md`).

## Status

Backlog. Hot M007 candidate. **Recommended replacement** for `archives-flag.md` (absorbs it). Sibling to `areas-bucket.md` and `domain-frontmatter.md`. Soft prerequisite for `lx-vault-merge.md` Phase 2.

Lineage: lifted from operator's own 2026-05-02 vault-architecture plan (`imported/lx/plan/vault/vault-architecture.md`), specifically the "compile.py vs scan-vault.py" question and the implicit gap around where deliberate human long-form writes belong.
