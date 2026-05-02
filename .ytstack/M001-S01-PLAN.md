---
milestone: M001
slice: S01
project: llm-wiki
created: 2026-05-02T11:35:00Z
status: in_progress
---

# M001 / S01 — Install seeds + skill-symlinks

## Goal

`install.sh` produces a vault that's immediately usable in Obsidian — the operator doesn't have to hand-create AGENTS.md, dashboard.md, or `.obsidian/` plugin lists, and Claude Code automatically sees the engine's skills.

## Tasks

### T01 — Create `templates/` dir + AGENTS.example.md

Derive a generic article-schema template from the existing vault's `AGENTS.md`. Strip personal content (folder taxonomies tied to operator's data, specific person/project examples). Keep: schema spec, frontmatter conventions, naming rules, compile-prompt-relevant structure.

**Files:** `templates/AGENTS.example.md` (new).

**Verify:** file exists; opens cleanly in any editor; no `lxw`, `alex`, person-name, or project-name leaks; renders sensibly in a fresh-vault context.

### T02 — Create `templates/dashboard.md`

Derive from existing vault dashboard. Use Dataview queries that work in any vault (`raw/**`, `daily/**`, `knowledge/**`). No hardcoded vault-specific filters.

**Files:** `templates/dashboard.md` (new).

**Verify:** file exists; queries reference only standard llm-wiki folder layout; opens in Obsidian and shows results when Dataview is enabled.

### T03 — Create `templates/.obsidian/community-plugins.json` + `core-plugins.json`

community-plugins: `["dataview", "obsidian-excalidraw-plugin"]` — the two plugins the engine actively benefits from. Operator approves install on first Obsidian launch.

core-plugins: minimal opinionated patch matching how llm-wiki uses Obsidian — `daily-notes: true`, `templates: true`, `properties: true`, `bookmarks: true`, `outline: true`. Defaults that are off can stay off.

**Files:** `templates/.obsidian/community-plugins.json`, `templates/.obsidian/core-plugins.json` (both new).

**Verify:** valid JSON; opening a fresh vault that uses these files works in Obsidian (plugins listed, awaiting approval).

### T04 — Extend `install.sh` to seed templates

For each `templates/<file>`: if `<target>/<file>` does NOT exist, copy. Never overwrite.

Specifically: `templates/AGENTS.example.md` → `<target>/AGENTS.md`; `templates/dashboard.md` → `<target>/dashboard.md`; `templates/.obsidian/*.json` → `<target>/.obsidian/*.json` (mkdir `.obsidian/` if absent).

**Files:** `install.sh` (modified — add a seeding block after the config-seed step).

**Verify:** `./install.sh /tmp/test-vault-$(date +%s)` on a fresh dir creates AGENTS.md, dashboard.md, .obsidian/community-plugins.json, .obsidian/core-plugins.json at the target. Re-running on a populated vault doesn't overwrite.

### T05 — Extend `install.sh` to create skill-symlinks

For each dir in `<.wiki>/skills/<name>/`: create symlink `<target>/.claude/skills/<name>` → `../../.wiki/skills/<name>` (relative path from the symlink's parent — `.claude/skills/` is two levels deep, so `../../.wiki/skills/<name>` resolves correctly). Skip if symlink already exists.

mkdir `<target>/.claude/skills/` if absent.

**Files:** `install.sh` (modified — add a symlink block after the seeding block).

**Verify:** post-install, `ls -la <target>/.claude/skills/` shows symlinks for every shipped skill; `readlink <target>/.claude/skills/<name>` resolves to `../../.wiki/skills/<name>`; symlinks point to existing dirs.

### T06 — Smoke test

Run: `bash install.sh /tmp/test-vault-$(date +%s)` (with `LLM_WIKI_REPO=$(pwd)` so it clones the local checkout — or, easier, copy the local checkout into place, since we don't want to push and re-clone for every test).

Confirm: vault has `AGENTS.md`, `dashboard.md`, `.obsidian/community-plugins.json`, `.obsidian/core-plugins.json`, `.claude/skills/{engine-pr,excalidraw-diagram,ingest-audio,vault-health-check,vault-triage}` (symlinks), and `.wiki/.venv/`. Run `uv run --project <vault>/.wiki python -c "import flush_pipeline; print('ok')"` and confirm output `ok`.

**Files:** none (verification only).

## Out of scope for S01

- Updating README.md to mention the new templates (deferred to S03 or a quick docs sweep)
- Re-rendering architecture.png if templates affect it (no expected impact)
- Seeding Excalidraw architecture diagram into the vault (out of scope; vault gets engine's `docs/architecture.excalidraw` if user wants it via separate copy)

## Verification commands (consolidated)

```bash
# After all tasks:
TEST_VAULT=/tmp/test-vault-$(date +%s)
LLM_WIKI_REPO=file://$(pwd) bash install.sh "$TEST_VAULT"

# Expectations:
test -f "$TEST_VAULT/AGENTS.md" && echo "✓ AGENTS.md"
test -f "$TEST_VAULT/dashboard.md" && echo "✓ dashboard.md"
test -f "$TEST_VAULT/.obsidian/community-plugins.json" && echo "✓ community-plugins.json"
test -f "$TEST_VAULT/.obsidian/core-plugins.json" && echo "✓ core-plugins.json"
for skill in $TEST_VAULT/.wiki/skills/*/; do
  name=$(basename "$skill")
  test -L "$TEST_VAULT/.claude/skills/$name" && echo "✓ skill-symlink: $name"
done
cd "$TEST_VAULT" && uv run --project .wiki python -c "import flush_pipeline; print('ok')"
```
