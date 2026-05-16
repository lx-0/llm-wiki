# Obsidian setup

The wiki engine writes and reads plain Markdown — any editor works. Obsidian
is the daily-driver UI because of graph view, backlinks, Dataview, and the
mobile apps. This doc covers desktop (macOS/Windows/Linux) and mobile
(iOS/Android), with the performance levers that matter once a vault has been
fed by collectors for a few weeks.

The engine seeds `.obsidian/` from `templates/.obsidian/` via `wiki seed`.
Per-client UI tweaks live in the vault and persist across re-seeds **only if
they were merged into `templates/.obsidian/`** — see "Persisting settings
across `wiki seed --force`" at the end.

## Desktop (macOS / Windows / Linux)

### 1. Open the vault

Obsidian → **Open folder as vault** → point at `<vault>` (the directory
containing `knowledge/`, `raw/`, `daily/`, `.wiki/`). On macOS the
recommended location is the iCloud-Drive Obsidian container so the same
vault appears on iPhone/iPad automatically:

```
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault-name>/
```

Any local path works too if you don't want iCloud — sync is then your
responsibility (Syncthing, git, Obsidian Sync, etc.).

### 2. Core plugins (seeded by `wiki seed`)

The engine pre-configures the plugins it depends on (Dataview, Templater,
Tasks, Excalidraw, Meta Bind, Extended Graph, …) under `.obsidian/`. Don't
disable them unless you know what reads them — the wiki dashboard, graph
view, and capture buttons all use them.

If something looks broken after a fresh `wiki seed`, restart Obsidian once
so it re-reads `.obsidian/community-plugins.json`.

### 3. Desktop is not the bottleneck

On any laptop made in the last five years, desktop Obsidian opens a
multi-thousand-note vault in under a second. The rest of this doc is about
mobile.

## iOS (iPhone / iPad)

### 1. Open the vault

If your vault lives in the iCloud Drive Obsidian container (above), the iOS
app auto-detects it on launch — pick it from the vault list. If it lives
elsewhere, you need a different sync path (Obsidian Sync paid plan, or
Working Copy + git).

### 2. Pin the vault locally — the biggest fix

The single largest cause of "Obsidian takes 30 seconds to open" on iOS is
**not** Obsidian re-indexing — it's iOS offloading vault files to iCloud to
save space, then downloading them file-by-file when the app launches.
Apple's iCloud API gives Obsidian no way to bulk-pre-fetch, so the fix has
to happen in the Files app:

1. Open **Files** on iPhone/iPad.
2. Navigate **iCloud Drive → Obsidian**.
3. Long-press the vault folder (e.g. `lxw`).
4. Choose **Keep Downloaded** (cloud-with-down-arrow icon).

iOS now keeps every file in the vault materialised locally. Sync still runs
bidirectionally — new files from the Mac come down, edits from the phone go
up — but there's no "stub → download on demand" stall at startup.

Trade-off: the vault footprint on the iPhone grows to its full disk size.
Check **Settings → General → iPhone Storage → Obsidian / Files** after a
few days. For a several-GB vault this is usually fine on a modern phone.

### 3. Exclude substrate folders from indexing

Obsidian indexes every Markdown file in the vault by default. For an
LLM-wiki vault, most of that index churn comes from `raw/` (substrate that
the engine writes constantly) and old `daily/` folders — neither of which
you typically search or graph from the phone.

**Settings → Files & Links → Excluded files** — the engine ships `raw/`
as a default exclusion via `templates/.obsidian/app.json`, so a fresh
`wiki seed` already excludes it on every client. Add more if you want:

- (already in template) `raw/`
- (optional) `daily/` if you only consume current-week digests

Caveats:

- This setting is stored in `.obsidian/app.json` and **applies to every
  client that opens the vault**, including desktop. That's usually what you
  want for `raw/` (substrate, not knowledge), but be deliberate.
- "Excluded files" hides them from Quick Switcher, Graph, Search, and
  unlinked-mention checks. Direct wikilinks still resolve. The collectors
  still write into the folder normally.

### 4. Disable heavy plugins on mobile only

Each community plugin has a per-platform toggle. The two repeat offenders
for cold-start latency are **Dataview** and **Tasks** queries that are
already open in the active note when you closed the app — Obsidian resolves
the queries before showing the editor.

**Settings → Community plugins → click each plugin** → toggle **"Disable
on mobile"** for anything you don't need on the phone (e.g. Excalidraw
editing, complex Dataview boards, Templater scripts you only invoke from
desktop).

Habit fix: before closing Obsidian on iOS, switch to a plain note (no
Dataview/Tasks blocks) so reopening doesn't trigger a query resolve.

### 5. Verify the IndexedDB-flush fix is in

Obsidian ≤ 1.8.7 had a bug where the persisted index was silently lost on
large vaults, forcing a full reindex every launch. Fixed in 1.8.8.

**Settings → About → Current version** → must be **≥ 1.8.8** (ideally
1.10+). Update via the App Store if not.

### 6. Diagnose what's actually slow

**Settings → General → Advanced → clock icon** (top right of the settings
modal in Obsidian ≥ 1.7.1) toggles the **Startup Time overlay**. Next
cold-start shows ms-by-component on screen: vault load, metadata cache,
each community plugin. Disable plugins one at a time and watch the overlay
move — don't guess.

## Android

The default llm-wiki vault path uses iCloud Drive, which Android can't read.
To use Obsidian on Android against the same vault you need one of:

- **Obsidian Sync** (paid, ~$5/mo) — easiest, end-to-end encrypted, vault
  works identically on iOS + Android + desktop.
- **Syncthing** — free, peer-to-peer, requires a Mac/server reachable from
  the phone.
- **git** — clone the vault on the phone (e.g. via Termux), commit/push
  changes manually. Brittle with binary attachments.

Once the vault is on the device, the same mobile tips apply:

- "Keep Downloaded" has no equivalent — files are always local on Android
  with Sync/Syncthing/git, so the iCloud-offload class of bug doesn't
  exist.
- Excluded files (`raw/`, old `daily/`) — same setting, same effect.
- Disable heavy plugins on mobile — same toggle, same wins.
- Obsidian version ≥ 1.8.8 — App Store / Play Store update.

## Persisting settings across `wiki seed --force`

`.obsidian/*.json` defaults live in `templates/.obsidian/` in the engine
repo. When the operator runs `wiki seed --force`, those template files
overwrite vault-side edits.

If you want an engine-wide default (e.g. an additional excluded folder) to
survive re-seeds and reach every operator:

1. Make the edit in Obsidian as usual.
2. Diff `<vault>/.obsidian/app.json` vs the engine's
   `templates/.obsidian/app.json`.
3. Port the new key into the template, commit, push.
4. Next `wiki update` pulls it; new operators get the same default.

Note: `wiki seed` does **not** smart-merge `app.json` (unlike
`community-plugins.json` and `appearance.json`, which have explicit merge
helpers). So on `--force` the template file replaces the operator's file
wholesale. Keep operator-specific tweaks (personal hotkeys, theme tweaks)
in vault files the engine does not template.

## TL;DR checklist

- [ ] Vault in `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<name>/`
      (macOS + iOS), or sync solution chosen for Android.
- [ ] Obsidian ≥ 1.8.8 on every device.
- [ ] **Files app → vault folder → Keep Downloaded** (iOS).
- [ ] **Settings → Files & Links → Excluded files** → `raw/` added.
- [ ] Heavy plugins toggled **Disable on mobile** where appropriate.
- [ ] Active note at app-close is plain (no open Dataview/Tasks queries).
- [ ] Run **Startup Time overlay** once after the changes to confirm.
