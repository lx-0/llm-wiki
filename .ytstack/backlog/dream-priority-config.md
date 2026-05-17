# M017 — Dream-priority config: rules-based weighted entity selection

Operator-controlled selection priority for dream-cycle entities, declared as rules in `config.yaml` (centralized) with optional per-entity frontmatter override. Replaces the M014 default of "pick N most-overdue" with operator-shaped weighted-selection.

## Problem this solves

Current piggyback selection is greedy-by-age: every entity gets equal weight, oldest-untouched wins each run. That doesn't match operator priorities:

- Some entities are operator-anchors (alex.md = the operator's own profile) and should be dreamed more often than secondary entities
- Some entities are work-active (current customers, current projects) and need fresher synthesis than dormant ones
- Some entities are shipped/archived/retired and should be skipped (or near-zero priority) — keeping them in piggyback rotation wastes budget
- Operator wants to tune all this WITHOUT editing per-entity frontmatter for every page

## Architecture — rules in config.yaml, per-entity override via frontmatter

### Config schema (`config.yaml` → `scheduling.dream_priority`)

```yaml
scheduling:
  dream_cooldown_days: 7
  dream_priority:
    # base weight for any entity that doesn't match more-specific rules
    default: 1.0

    # explicit path/glob overrides — highest config-rule precedence (first-match-wins)
    paths:
      "knowledge/people/alex.md": 5.0
      "knowledge/people/sidney-wach.md": 2.5
      "knowledge/areas/personal-*-archived.md": 0   # never auto-dream
      "knowledge/projects/yesterday-os.md": 3.0

    # multipliers applied to the resolved base when entity matches the axis
    domain:
      personal: 1.5
      company: 1.8
      ai: 1.5
      meta: 0.5

    # tag-axis multipliers; tag_strategy controls multi-tag handling
    tag_strategy: max         # max | sum | first — when multi-tag matches
    tags:
      operator-anchor: 5.0
      work-active: 2.5
      shipped: 0.2
      archive: 0.1
      stale: 0.05

    # status-axis multipliers (M008 areas + similar status frontmatter)
    status:
      active: 1.0
      dormant: 0.3
      retired: 0.05
```

### Per-entity frontmatter override (absolute precedence)

```yaml
# in knowledge/people/X.md:
dream_priority: 0      # disable: never auto-dreamed, ignore all rules
dream_priority: 8.0    # spike: priority floor, overrides config-rules
```

### Resolution order

1. **Per-entity frontmatter `dream_priority:`** — if set (incl. `0`), use it. Skips all rules. Absolute control.
2. **`paths:` glob/exact match** — first-match wins. Glob via fnmatch.
3. **Formula**: `default × domain_multiplier × tag_multiplier_via_strategy × status_multiplier`. Multipliers default to `1.0` when axis isn't in config or entity doesn't have that axis-value.

### Tag-strategy options (when entity has multiple tags matching `tags:` config)

- `max` (default): take the highest tag-multiplier. Example: entity tagged `[work-active, ai-experiment]` with `tags: {work-active: 2.5, ai-experiment: 3.0}` → multiplier = 3.0.
- `sum`: add all matching tag-multipliers. Example: same case → multiplier = 5.5.
- `first`: take the first matching tag (frontmatter order). Brittle, only use if operator wants explicit ordering.

## Selection algorithm

Per piggyback run (or `wiki dream --all-entities`):

```python
def select_entities(N, mode="probabilistic"):
    eligible = []
    for entity in all_entity_pages():
        if in_cooldown(entity, days=CONFIG.scheduling.dream_cooldown_days):
            continue
        weight = compute_priority(entity) * age_days_since_last_synth(entity) * jitter(0.85, 1.15)
        if weight <= 0:
            continue   # priority:0 = excluded
        eligible.append((weight, entity))

    if mode == "probabilistic":
        weights = [w for w, _ in eligible]
        return random.choices(eligible, weights=weights, k=min(N, len(eligible)))
    else:  # "greedy"
        return [e for _, e in sorted(eligible, reverse=True)][:N]
```

### Selection mode (`piggybacks.dream_cycle.selection_mode`)

- **`probabilistic`** (default): weighted-random-sample. Diversity over time — every eligible entity eventually selected, biased toward high-weight. Better for steady-state piggyback usage.
- **`greedy`**: top-N by weight. Deterministic, predictable. Good for one-off sweeps where operator wants the highest-priority entity guaranteed-first.

## CLI surface

```bash
wiki dream --list-candidates
# Prints sorted ranking with weight breakdown:
#   Rank  Weight   Last-Dreamed  Slug                              Source
#   1     35.4     7d ago        knowledge/people/alex             paths:5.0 × age:7d × jitter:1.01
#   2     12.0     5d ago        knowledge/people/sidney-wach      paths:2.5 × age:5d × jitter:0.96
#   3     9.5      2d ago        knowledge/projects/yesterday-os   paths:3.0 × age:2d × jitter:1.05 (M017-config)
#   ...
#   N     0.0      —             knowledge/areas/personal-old      paths:0 → EXCLUDED
```

Lets operator debug config rules + see priority landscape one-view.

## Implementation surfaces

- `scripts/core/config.py` — new `DreamPriority` dataclass nested under `Scheduling` (paths dict, domain dict, tags dict, status dict, tag_strategy enum, default float)
- `scripts/dream.py` — new `compute_entity_priority(entity, config)` helper + extend `select_for_sweep()` with mode-switch
- `scripts/dream.py` — `--list-candidates` CLI flag for `wiki dream` subcommand
- `config.example.yaml` — full `dream_priority:` example block with operator-facing comments
- `scripts/migrations/migrate_config_keys.py` — KEY_ADDITIONS for the new `dream_priority` block (same-commit per project hard-rule)
- `tests/test_dream_priority.py` — covers: per-entity override precedence, path-glob matching, domain/tag/status multipliers, tag_strategy (max/sum/first), cooldown still blocks, weight=0 excludes, probabilistic vs greedy selection
- `AGENTS.md` — short section on dream-priority (operator-facing convention)
- `prompts/agents/dream-cycle.md` — if it references piggyback selection, update to mention config-driven priorities

## Out of scope (future)

- Dynamic SQL-style rule expressions (`dream_priority_query: "CASE WHEN domain='personal' AND kind='concept' THEN 2.0..."`) — too heavy, defer
- Tag-based topic-clustering (`wiki dream --tag openclaw` sweeps all openclaw-tagged) — separate M018 candidate
- Recursive dream-cycle (weekly→monthly digests) — separate M019 backlog item
- Learned weights from operator interaction patterns (operator-edit-frequency, search-frequency boost dream weight) — research-territory, defer

## Lift estimate

- Config + dataclass + migration entry: 1 hour
- Resolution engine (compute_entity_priority + glob match): 1 hour
- Selection mode switch (probabilistic vs greedy): 30 min
- CLI `--list-candidates`: 30 min
- Tests: 1.5 hours (rules-engine has many branches)
- Docs (AGENTS.md + memory pointer + this backlog file marked shipped): 1 hour

**Total: ~5-6 hours (~1 day) end-to-end with care.**

## Risks

1. **Rules-config drift over time** — operator sets rules once, forgets, behavior surprises later. Mitigation: `wiki dream --list-candidates` makes ranking observable; operator can audit anytime.
2. **Per-entity frontmatter override forgotten** — operator sets `dream_priority: 8.0` on alex, six months later wonders why config rules don't apply. Mitigation: list-candidates output marks override-source per entity (config-rule vs frontmatter-override).
3. **Glob patterns brittle** — operator typos a path pattern, no entities match silently. Mitigation: lint check warns when a `paths:` rule matches 0 entities.
4. **Probabilistic mode loses high-prio determinism** — operator wants alex EVERY dream, but probabilistic gives weighted-random so alex MOSTLY (not always) selected. Mitigation: operator picks greedy mode if determinism matters, OR sets per-entity dream_priority very high so it's always-top.

## Status

Backlog → in implementation (2026-05-17).
