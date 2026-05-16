---
title: Smart-merge for templates/.obsidian/app.json in seed.sh
status: backlog
surfaced: 2026-05-16
size: XS
---

## Problem

`lib/seed.sh` (around line 268) loops over `templates/.obsidian/*.json` and
calls `_seed_file` for each — additive on `wiki seed` (skips existing
files), wholesale replacement on `wiki seed --force`.

Two of the three `.obsidian/*.json` files have explicit smart-merge
helpers:

- `community-plugins.json` → `_merge_community_plugins` (union)
- `appearance.json` → `_merge_appearance_json`
- `app.json` → **plain `_seed_file`** ← fall-through, no merge

This was acceptable while the engine didn't ship an `app.json` template
(commit `fb1ecf6` is the first one — `userIgnoreFilters: ["raw/"]`). Now
that the template exists, the gap becomes visible:

- **Fresh install:** fine — template is the only source.
- **Plain `wiki seed` on existing vault:** fine — operator's `app.json` is
  skipped, but they also don't pick up future engine defaults until they
  diff manually.
- **`wiki seed --force` on existing vault:** **template replaces
  operator-customised `app.json` wholesale.** Operator-specific hotkeys,
  trash settings, vault display name, attachment folder path, etc. are
  silently dropped.

## Proposed fix

Add `_merge_app_json` in `lib/seed.sh` modeled on `_merge_community_plugins`:

- Read operator's `app.json` (or `{}` if missing).
- Read template's `app.json`.
- For each key in template:
  - If key not present in operator file → copy in.
  - If `userIgnoreFilters` specifically → union (don't lose operator's
    extra exclusions).
  - Otherwise → leave operator's value as-is (template is only a default,
    not an override).

Wire it into the `.obsidian/*.json` loop next to the existing two helpers.

## Tests

`tests/test_seed_app_json_merge.py` (new):
- Operator has `{}` → result equals template.
- Operator has unrelated keys → keys preserved, template defaults added.
- Operator has `userIgnoreFilters: ["custom/"]` + template has
  `["raw/"]` → result has both.
- `--force` does not blow away operator-only keys.

## Defer rationale

Single-operator engine right now (lxw). Operator's `app.json` only has the
single `userIgnoreFilters: ["raw/"]` key — identical to template, no
collision risk. Implementing the merge before there's a second operator
with a non-trivial app.json is YAGNI. Bump to "do" when:

- A second operator onboards with a custom `app.json`, OR
- The engine adds a second `app.json` key (e.g. `attachmentFolderPath`
  defaulting to `raw/attachments/`) and risks colliding with operator
  setups.
