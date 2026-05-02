---
name: Auto-symlink engine skills into vault .claude/skills/ during install
description: install.sh currently scaffolds the .wiki/ engine but doesn't surface its skills (vault-triage, ingest-audio, vault-health-check, …) to Claude Code. Each install requires manual symlinking from <vault>/.claude/skills/<skill> → ../../.wiki/skills/<skill>. Move that into install.sh so every clean install gets the skills wired up automatically.
type: feature
origin: vault-observation
created: 2026-05-02
---

# Auto-symlink engine skills into vault `.claude/skills/`

## Problem

The engine ships skills under `.wiki/skills/<skill>/SKILL.md` (currently
`vault-triage`, `ingest-audio`, `excalidraw-diagram`, soon `vault-health-check`).
Claude Code only discovers skills under `<project>/.claude/skills/<skill>/`,
not under `<project>/.wiki/skills/`. So in a fresh install the engine's skills
are present but invisible — the operator has to manually:

```sh
mkdir -p <vault>/.claude/skills
ln -s ../../.wiki/skills/<skill> <vault>/.claude/skills/<skill>
```

…for every skill, on every machine.

## Why the symlink is the right shape

The Single-Skill-Repo convention from the wider stack (gstack, ytstack, etc.)
is to symlink the whole skill folder. Quoting the user's global
`CLAUDE.md`:

> Single-Skill-Repo: ganzer Ordner symlinked — `~/.claude/skills/<name>` →
> `/path/to/repo/skills/.../<name>`. Simpler, funktioniert weil der
> Quell-Ordner genau ein Skill ist.

Same pattern fits here, just at project-scope (`<vault>/.claude/skills/`)
instead of user-scope (`~/.claude/skills/`).

The alternative — copying the SKILL.md — would drift on every engine update.
The symlink keeps the skill canonically owned by the engine repo.

## Proposed install.sh extension

After the engine clone (or `pull`) step in `install.sh`, add:

```sh
mkdir -p "$VAULT_ROOT/.claude/skills"
for skill_dir in "$VAULT_ROOT/.wiki/skills"/*/; do
    skill_name=$(basename "$skill_dir")
    target="$VAULT_ROOT/.claude/skills/$skill_name"
    relative="../../.wiki/skills/$skill_name"

    if [[ -L "$target" ]]; then
        # already a symlink — re-point in case the engine renamed/moved it
        ln -sfn "$relative" "$target"
    elif [[ -e "$target" ]]; then
        # exists but isn't a symlink — local override, leave it alone, warn
        echo "⚠ $target exists and is not a symlink; skipping (local override?)" >&2
    else
        ln -s "$relative" "$target"
        echo "✓ linked $skill_name"
    fi
done
```

Idempotent: re-running install.sh (or a dedicated `install.sh --refresh-skills`
mode) is safe.

## Edge cases

- **Skill removed from engine.** A symlink in `.claude/skills/` whose target
  no longer exists becomes dangling. Add a `cleanup` pass that removes any
  symlink in `.claude/skills/` pointing into `.wiki/skills/` whose target is
  missing. Don't touch non-symlink entries (could be user-authored skills).
- **User-authored skills in `.claude/skills/`.** Leave them alone; the
  `[[ -L ]]` check above avoids overwriting non-symlinks.
- **Cross-platform.** `ln -s` works on macOS + Linux. Windows/WSL needs
  attention (developer-mode symlink permission); document as a known
  limitation if the engine targets that platform.
- **Vault inside a synced cloud folder (iCloud, Dropbox, Sync.app).**
  Symlinks generally survive Sync.app and Dropbox; iCloud's Mobile Documents
  has historically been wonky. Mention in the install docs.

## Touchpoints

- `install.sh` — new section after the `.wiki/` clone step.
- `docs/PROCESS.md` — short note that `.claude/skills/` is engine-managed.
- Optional new flag `install.sh --refresh-skills` for re-running just this
  section after an engine update introduces new skills.

## Open questions

- **User-scope vs. project-scope.** Should engine skills also be linked into
  `~/.claude/skills/` (user-global) so they're available in any Claude Code
  session, not just inside the vault? Argument for: vault-triage / ingest-audio
  are useful even when the operator is browsing the vault from outside. Argument
  against: a skill that depends on engine paths breaks loudly outside the vault.
  Default proposal: project-scope only; user can manually elevate.
- **Skill-discovery hint in the engine.** Should each `SKILL.md` include a
  trailer comment noting its expected install path, so a misplaced skill
  surfaces a useful error? (Probably overkill for now.)

## Source

Surfaced 2026-05-02 during a vault-state conversation, alongside the creation
of the `vault-health-check` skill — the request was to push a change request
upstream so that the wiki engine's `install.sh` (or equivalent setup step)
creates the agent skill-symlinks automatically rather than relying on the
operator to wire them up post-install.
