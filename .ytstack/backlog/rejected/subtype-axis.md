# Subtype Axis — split `concepts/` into 6 meaningful color groups

**Status (2026-05-15):** Deferred in favor of Extended Graph plugin (tag-arcs + type-shapes) which solves the multi-channel problem without schema migration. Subtype-axis remains a possible later refinement if (a) the engine grows lint/dataview needs that benefit from a single-valued shape field, or (b) a vault drops Extended Graph and reverts to native graph only.

---


A second classification axis on `knowledge/` notes: a `subtype:` frontmatter field that distinguishes *what shape of knowledge* a note is, orthogonal to the folder-typed `type:` field. Solves the "87% indigo" problem in the Obsidian graph view — see screenshot session 2026-05-15.

## The problem

`templates/.obsidian/graph.json` color-groups query by `path:`. The lxw vault has 968 knowledge notes distributed as:

| Folder | Count | % |
|---|---|---|
| concepts/ | 840 | 87% |
| connections/ | 58 | 6% |
| projects/ | 44 | 5% |
| people/ | 19 | 2% |
| MOCs/ | 3 | 0.3% |
| facts/ | 2 | 0.2% |

→ 87% of all nodes carry the same color. The 5 other color groups paint noise. Independent of the lateral-linking problem (`concepts/` → `concepts/` = 0 wikilinks).

The `type:` frontmatter field exists already — but mirrors the folder (`type: concept` for all 840 concepts). It's currently redundant.

## What changes

Introduce a **second, additive** axis: `subtype:` — a closed enum that classifies the *shape* of a note:

```yaml
subtype: gotcha | pattern | principle | decision | technique | reference
```

| Subtype | Meaning | Tag-heuristic for backfill |
|---|---|---|
| `gotcha` | A documented failure / anti-pattern (what went wrong) | tags include `gotcha`, `bug`, `incident`, `pitfall` |
| `pattern` | A reusable solution (what works) | tags include `pattern`, `recipe`, `idiom` |
| `principle` | A rule or discipline (how we decide) | tags include `discipline`, `principle`, `rule`, `convention` |
| `decision` | A specific made choice + rationale (why so, not otherwise) | tags include `decision`, `adr`, `choice` |
| `technique` | A workflow / method (how we do it) | tags include `workflow`, `technique`, `method`, `process` |
| `reference` | Factual lookup (what is X) | fallback when none of the above match |

`subtype:` is **only meaningful inside `concepts/`** (840 notes). For `people/`, `projects/`, `connections/`, `MOCs/`, `facts/` the folder + `type:` is already specific enough — `subtype:` is optional / absent there.

## Why this shape (and not alternatives)

- **Not "split concepts/ into subfolders"** — that breaks every memory/skill path reference, requires re-classifying 840 files into mutually exclusive folders, and complicates the compile-routing decision. Frontmatter-axis is additive, reversible, doesn't break Dataview queries on `type:`.
- **Not "use tags for color"** — tag color-groups would have to first-match-win across 5 tags/note, which is noisy. `subtype:` is single-valued per note, deterministic.
- **Not "redefine `type:`"** — existing Dataview queries, lint, dashboard charts depend on `type:` matching the folder (single source of truth, declared in `prompts/compile_main.md:46`). Breaking that costs more than the new field saves.
- **Not "adopt gbrain's 19 folders"** — operator-specific to Garry Tan's VC world. We don't have `deals/`, `civic/`, `household/`. The transferable insight is "every note has one shape" — implemented via frontmatter is cheaper than via folders.

## How it integrates

### Compile prompt (`prompts/compile_main.md`)

Add a new rule next to the existing `type:` mapping:

> For articles created in `knowledge/concepts/`, additionally emit a `subtype:` field with one of: `gotcha`, `pattern`, `principle`, `decision`, `technique`, `reference`. Pick the shape that best matches what the article *teaches*:
> - `gotcha` — describes a failure mode, surprise, anti-pattern
> - `pattern` — describes a reusable solution
> - `principle` — states a rule the operator follows
> - `decision` — records a specific choice with rationale
> - `technique` — describes a method or workflow
> - `reference` — pure factual lookup (default if unsure)

### Lint (`scripts/lint.py`)

New check `check_article_subtype()` (analog to existing `check_article_type` at line 233):

- For each article in `knowledge/concepts/`: verify `subtype:` exists and is one of the 6 enum values
- Severity: `warning` if missing (not `error`) — backfill is gradual, not blocking
- Severity: `error` if value is outside the enum (catches typos)
- Auto-fixable: false (this needs human or heuristic-script judgment)

### Backfill script (`scripts/links/backfill_subtype.py` — new)

Deterministic tag-heuristic backfill for the 840 existing concepts. No LLM call.

```python
SUBTYPE_HEURISTICS = {
    "gotcha":    ["gotcha", "bug", "incident", "pitfall", "anti-pattern"],
    "pattern":   ["pattern", "recipe", "idiom"],
    "principle": ["discipline", "principle", "rule", "convention"],
    "decision":  ["decision", "adr", "choice"],
    "technique": ["workflow", "technique", "method", "process"],
}

def classify(tags: list[str]) -> str | None:
    # First-match-wins in enum order
    for subtype, markers in SUBTYPE_HEURISTICS.items():
        if any(tag in markers for tag in tags):
            return subtype
    return None  # leave unclassified — operator or compile-pass decides later
```

CLI: `wiki backfill subtype --dry-run` / `wiki backfill subtype apply`. Idempotent (only fills empty `subtype:` fields, never overwrites).

Expected coverage from a first probe on lxw tag-frequencies:
- gotcha: ~42 (tag freq for `gotcha`)
- pattern: ~24
- principle: ~26+
- decision: <20 (no dominant tag, will mostly stay unclassified)
- technique: ~55 (tag `workflow`)
- reference: 0 (fallback only)
- **Total ~170-200 backfilled deterministically** (20-25% of concepts/)

The other ~640 stay `subtype: <missing>` and either:
- Get classified by the next `wiki compile` pass when the source-substrate is re-touched
- Get LLM-batch-classified in a later optional pass (out of this scope)

### Color groups (`templates/.obsidian/graph.json`)

Replace the single `path:knowledge/concepts` group with 6 subtype-queried groups. Keep the existing 5 folder-queried groups for people/projects/MOCs/connections/facts.

New palette additions (Material colors, no clash with existing 6):
- `gotcha` → red-deep (warning)
- `pattern` → green (positive)
- `principle` → purple (authority)
- `decision` → blue (cool)
- `technique` → teal (cool-action)
- `reference` → grey (neutral)

Existing concept-indigo gets retired — but the `path:knowledge/concepts` query can stay as a fallback group at lowest priority for unclassified notes (covers backfill-gap).

### Config (`scripts/core/wiki_config.py` + `config.example.yaml`)

```yaml
schema:
  concept_subtypes:
    - gotcha
    - pattern
    - principle
    - decision
    - technique
    - reference
```

Allows operator to extend the enum without code edit. Lint reads this list.

## Affected scripts (Phase-2 verify list)

- `prompts/compile_main.md` — new rule, ~10 lines
- `scripts/lint.py` — new `check_article_subtype()`, ~30 lines
- `scripts/links/backfill_subtype.py` — new file, ~80 lines
- `scripts/core/wiki_config.py` — new `SchemaConfig.concept_subtypes`, ~5 lines
- `wiki` (CLI dispatcher) — new `backfill subtype` subcommand, ~5 lines
- `templates/.obsidian/graph.json` — 6 new color groups, retire concepts/ path-group
- `templates/config.example.yaml` — new `schema:` section
- `templates/AGENTS.example.md` — schema doc updated, +10 lines

## Edge cases & failure modes

1. **A note has multiple matching tag heuristics** (e.g. tags `[gotcha, pattern]`). → First-match-wins in enum order (gotcha before pattern). Documented in the script. Operator can `wiki correct apply` if wrong.
2. **A note has no matching tags.** → `subtype:` stays empty. Lint warns. No data loss.
3. **Operator types a subtype outside the enum.** → Lint errors. `wiki correct apply` is the manual fix path.
4. **Compile-prompt forgets to emit `subtype:` for a new concept.** → Lint warns next run. Backfill heuristic runs on commit-hook (optional) to fill from tags.
5. **Subtype field added to non-concept folder (people/, etc.).** → Lint ignores; field is technically allowed but semantically empty. No harm.
6. **Existing Dataview queries on `type:`** → unaffected; this is a new field.
7. **Graph color group ordering** → Obsidian applies first-matching group. New subtype-groups must precede the `path:knowledge/concepts` fallback group, otherwise everything stays indigo.
8. **Vault upgrade story** — vaults that update via `wiki update` need the new `templates/.obsidian/graph.json` applied. Memory `[feedback_obsidian_config_via_template]` already says edits in `.obsidian/` don't survive `wiki seed --force` — so the operator's manual graph.json gets overwritten on next force-seed. Document this in the change-log.

## What this does NOT do

- Does not change folder structure (no `concepts/gotchas/`, etc.)
- Does not introduce LLM call in backfill (deterministic only)
- Does not touch `type:` field semantics
- Does not add lateral wikilinks (that's the separate Stufe-1 work)
- Does not auto-classify the ~640 notes without matching tags (deferred to later passes)

## Ripens

Immediately — the graph-view pain is live, the data shape supports the heuristic, no prerequisites.

## Out-of-scope follow-ups

- LLM-based batch-classification of the unclassified ~640 concepts (separate one-shot pass, $5-15 cost)
- Subtype-aware lateral linking (the "Stufe 1" work — once subtype lands, lateral-linker can prefer same-subtype matches with bonus weight)
- Subtype for people/projects (e.g. `subtype: customer|colleague|investor` for people/) — only if pain emerges there
