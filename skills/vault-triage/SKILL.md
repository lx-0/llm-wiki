---
name: vault-triage
version: 1.0.0
description: |
  Triage notes in an Obsidian vault's inbox into the PARA structure. Reviews
  pending notes, suggests categorization (top-level area, PARA level, subfolder),
  and moves files on approval. Learns from corrections.
  Use when: user says "triage", "sort inbox", "clean inbox", "einsortieren".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Vault Triage — sort inbox into PARA

## Overview

Reviews pending notes in the vault's inbox and moves them into the [PARA structure](https://fortelabs.com/blog/para/) (Projects / Areas / Resources / Archives) with per-item user approval. Learns from corrections so future suggestions improve.

## Configuration

The skill needs to know two things about the user's vault — both via env vars:

```bash
VAULT="${VAULT_ROOT:?VAULT_ROOT must be set to your Obsidian vault path}"
INBOX="${INBOX_DIR:-Inbox}"        # Folder name relative to VAULT (e.g. "Inbox" or "📥 Inbox")
```

Top-level **areas** are user-specific — the skill discovers them at runtime by listing top-level directories in `$VAULT` (skipping `_attachments` and dotfiles). It learns the user's naming convention (with or without emoji prefix) from prior triage decisions.

Within each top-level area, the four PARA folders:

```text
<area>/
├── Projects/    ← has a goal AND a deadline
├── Areas/       ← ongoing sub-responsibility
├── Resources/   ← reference material
└── Archives/    ← done / inactive
```

## Triage flow

### Step 1 — scan inbox

```bash
ls "$VAULT/$INBOX"
```

For each file:
1. Read content + frontmatter.
2. Determine categorization (Step 2).
3. Present suggestion (Step 3).
4. Move on approval (Step 4).

### Step 2 — categorize

For each note, determine four things:

**Area** — which top-level area? Discover available areas with `ls -d "$VAULT"/*/ | grep -v _attachments`. Match content to area:
- *business / work* → Company-style area
- *private / hobbies / lists* → Personal-style area
- *AI tooling / generated content / agents* → AI-style area
- *anything else* → user-defined area

**PARA level**:
- `Projects/` — has a goal AND a deadline; create a subfolder if needed
- `Areas/` — ongoing sub-responsibility; use existing subfolder or create new
- `Resources/` — reference material, look-up content
- `Archives/` — done, inactive, outdated

**Subfolder** — check existing first: `ls "$VAULT/<area>/Areas/"`. Suggest existing folder when content fits; suggest a new subfolder only if nothing fits.

**Rename** — only if the filename is generic (`Untitled`, `Unbenannt`, …); otherwise keep.

### Step 3 — present to user

`AskUserQuestion` per file (or batch similar files). Show:
- Filename + 1–2-sentence content summary
- Suggested target: `<area>/<PARA>/<subfolder>/`
- Suggested rename (if applicable)
- Options: Approve / Change target / Skip / Archive

For **audio + companion .md pairs** (`.mp3`, `.m4a`, etc. with a same-stem `.md`):
- Move the audio to `<target>/_attachments/`
- Move the companion `.md` to `<target>/`
- Keep the `![[audio.mp3]]` embed working

### Step 4 — move on approval

```bash
mv "$VAULT/$INBOX/<filename>" "$VAULT/<area>/<PARA>/<subfolder>/"

mkdir -p "$VAULT/<area>/<PARA>/<subfolder>/_attachments"
mv "$VAULT/$INBOX/<audio_file>" "$VAULT/<area>/<PARA>/<subfolder>/_attachments/"
```

After moving:
- If frontmatter has `status: review` → flip to `status: approved`.
- If renamed, update incoming `[[wikilinks]]` (use Grep to find them).

### Step 5 — learn from decision

Append the decision to the triage learning log at `$VAULT/.claude/triage-log.yaml`:

```yaml
- date: "2026-01-15"
  file: "<filename>"
  type: <type>
  tags: [...]
  suggested: "<area>/Resources/"
  accepted: "<area>/Areas/<subfolder>/"
  correction: true
  reason: "User puts philosophy content under Areas, not Resources"
```

Fields:
- `suggested` — what the skill suggested
- `accepted` — where it actually went
- `correction` — true if suggestion was wrong
- `reason` — why the user chose differently (inferred or asked)

### Step 6 — use learning log for future suggestions

Before categorizing a new file:

```bash
cat "$VAULT/.claude/triage-log.yaml" 2>/dev/null
```

Apply the log:
- **Pattern match** — if similar content (same tags, type, keywords) was corrected before, apply the corrected path.
- **Folder affinity** — if the user consistently routes `tags: [philosophy, vision]` to a specific subfolder, learn that association.
- **Avoid repeated mistakes** — never suggest the same wrong path twice for similar content.
- **Surface confidence** — when presenting, note if a suggestion is based on a learned pattern: "→ `<subfolder>` (based on prior decision)".

### Step 7 — summary

After all files are processed:
- N sorted, where they went
- N skipped, N archived
- N remaining in inbox
- N suggestions based on learned patterns

## Rules

- **Always ask before moving** — never auto-sort without user approval.
- **Always suggest** — every file gets a recommendation with reasoning.
- **Learn from corrections** — every override is logged and improves future suggestions.
- **Batch similar items** — present 3+ obviously-same-area items together.
- **Audio + note pairs always move together** — audio into `_attachments/`.
- **Empty / junk files → Archives/**, not deletion.
- **Max one new subfolder level** — don't create deep nesting on the fly.
- **Preserve wikilinks** — if renaming, fix incoming links.
- **Show confidence source** — tell the user when a suggestion comes from a learned pattern.

## Example

```text
User: /vault-triage

Scanning <inbox>/ ... 5 files found.
Loading triage log ... 12 prior decisions, 3 corrections.

1. "Vision 2027.md"
   Strategy doc on long-term direction.
   → <area>/Areas/<vision-subfolder>/
   💡 Learned: similar to a prior file with tags [strategy, vision]
   [Approve] [Change] [Skip]

2. "Untitled 1.md" (59 bytes, near-empty)
   → Archives/
   [Approve] [Skip]

3. "Side project idea.md" (business idea, no deadline yet)
   → <area>/Projects/<new-subfolder>/
   [Approve] [Change] [Skip]
```
