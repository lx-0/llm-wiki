# Seed drift detection: semantic JSON-diff for `.obsidian/`-managed files

**Triggered by:** vault drift audit 2026-05-13. `wiki seed --check` currently uses `cmp -s` (binary equality). For Obsidian-plugin-edited files this produces near-100% false-positives because Obsidian touches the JSON the moment it opens the vault.
**Priority:** P2 — refinement, not blocking. Engine works; audit just has noise.

## Problem

`_seed_file` in `lib/seed.sh` compares engine template vs vault file byte-for-byte. For plain-text Markdown templates (README, AGENTS) that's fine. For `.obsidian/*.json` / `.obsidian/plugins/*/data.json`, the comparison is misleading:

| File | Real source of "drifted" | Engine-relevant? |
|---|---|---|
| `.obsidian/graph.json` | Operator's UI state: `collapse-color-groups`, `collapse-forces`, `scale` (zoom level), `collapse-filter` | No — these are runtime UI persisted state |
| `.obsidian/plugins/quickadd/data.json` | QuickAdd auto-populated `providers[]` with OpenAI model catalogue on first settings open; plus pretty-print reformat | No — plugin runtime state |
| `.obsidian/plugins/obsidian-shellcommands/data.json` | Operator changed one icon (`calendar-clock` → `bot`) | No — trivial UX preference |
| `.obsidian/core-plugins.json` | Operator enabled `bases: true` for a plugin we ship a `.base` file for | Should be in engine template (separate ticket: see commit landing alongside this backlog entry) |

In the 2026-05-13 audit, 5 of 6 reported drifts were structural noise; only `knowledge.base` + `core-plugins.json` were real engine-template-stale.

## Proposed approach

Per-file diff strategy declared in seed.sh itself:

```bash
# In _seed_file or a sibling helper:
case "$rel_path" in
  .obsidian/graph.json)
    # Compare only the engine-relevant subset: search query, colorGroups,
    # node-size knobs we set deliberately. Ignore UI state.
    _diff_json_subset "$src" "$dst" '.search, .colorGroups, .nodeSizeMultiplier'
    ;;
  .obsidian/plugins/quickadd/data.json)
    # Compare choices[] only — ignore .ai.providers (plugin runtime).
    _diff_json_subset "$src" "$dst" '.choices'
    ;;
  .obsidian/plugins/obsidian-shellcommands/data.json)
    # Compare shell_commands[*].shell_command (the actual command string)
    # and id only — ignore icon, alias, confirm_execution prefs.
    _diff_json_subset "$src" "$dst" '.shell_commands | map_values({shell_command, working_directory})'
    ;;
  *)
    # Existing cmp -s for everything else (Markdown, etc.).
    cmp -s "$src" "$dst"
    ;;
esac
```

Helper `_diff_json_subset src dst jq_expr`:
- `jq "$jq_expr" "$src"` vs `jq "$jq_expr" "$dst"`
- Pretty-print + sort keys (`jq -S`) before comparing — kills formatting noise
- Return 0 if subsets match, 1 if drifted

## Acceptance criteria

- [ ] `wiki seed --check` against a fresh-out-of-box vault produces only "up-to-date" for `.obsidian/`-managed files
- [ ] Operator deliberately changing an engine-relevant subset (e.g. editing `graph.json` `search` query) still surfaces as drifted
- [ ] Operator changing UI state (zoom, collapse, icon prefs) does NOT surface as drifted
- [ ] The per-file `jq_expr` strategy is documented inline so future files can be added by pattern-match

## Out of scope

- Auto-merging operator changes into engine updates (just detect, don't merge)
- Diff-display in `wiki seed --check` output (current "drifted" tag is enough; deep diff is the operator's job via `git diff` or manual inspection)

## Cross-links

- `lib/seed.sh:_seed_file` — current binary cmp implementation
- Memory: `feedback_backlog_by_default.md` — why this is being filed at all instead of forgotten
