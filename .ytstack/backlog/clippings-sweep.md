---
name: Clippings sweep — pre-compile move from vault Clippings/ to raw/articles/
description: Vault-side change request. Obsidian Web Clipper drops files into Clippings/ which the pipeline doesn't see. Engine should sweep Clippings/ → raw/articles/ at compile-time and hint the user to reconfigure the browser extension default folder.
type: feature
origin: vault-observation
created: 2026-05-02
---

# Clippings Sweep — Pre-Compile Move

## Problem

A user installs [Obsidian Web Clipper](https://github.com/obsidianmd/obsidian-clipper) into the vault. It drops new clippings into the vault root `Clippings/` folder by default — that's the extension's hardcoded default destination.

`compile.py` does **not** include `Clippings/` in its source-glob (only `raw/**`, `daily/**`). So clipped articles are invisible to the pipeline until manually moved.

In practice this leaves clippings stranded — e.g. `Clippings/<title>.md` files with `tags: [clippings]` frontmatter that the compiler never sees.

## Why not "just configure the browser extension"

We can't. Web Clipper settings live in `chrome.storage.sync` (per-browser, per-profile) — there's no vault-side config file, no CLI hook, no install-time bootstrap we can run from the engine. The user must open the extension's options page and change the destination manually. That's a one-time action that's easy to forget on new browsers / new machines / after profile resets.

## Proposed feature

A pre-compile sweep step (inside `compile.py` or as a new `scripts/sweep-clippings.py` piggyback in `flush.py`):

1. Glob `<vault>/Clippings/*.md`
2. If > 0 files exist:
   - For each file: move to `<vault>/raw/articles/<sanitized-filename>.md` (use `Path.rename`; if vault is a git repo, prefer `git mv` so history follows)
   - Skip + warn (no overwrite) if the target name already exists in `raw/articles/`
   - Log: `INFO Moved N file(s) from Clippings/ to raw/articles/`
3. Once per vault, emit a one-shot hint (gated by a marker file `.wiki/scripts/state/clippings-hint-shown`):
   ```
   ℹ Tip: In the Obsidian Web Clipper browser extension, set the
     default folder to `raw/articles` directly — this sweep then
     becomes a no-op. Settings → General → Note location.
   ```
4. Frontmatter `tags: [clippings]` is preserved and serves as a source-marker for the compiled article.

## Edge cases

- **Filename collisions** — skip+warn, never overwrite. User resolves manually.
- **Sonderzeichen in filename** (`:`, `/`) — let downstream ingest sanitize, don't double-handle here.
- **`Clippings/` doesn't exist** — silent no-op.
- **User re-creates `Clippings/` folder** after the hint fired — the marker prevents the hint from re-firing on every run; sweep still runs.

## Touchpoints

- **Engine:** `scripts/compile.py` (sweep call at top of `main()`) **or** new `scripts/sweep-clippings.py` registered in `flush.py:PIGGYBACK_TASKS`. Piggyback variant is cleaner — runs on each session-end without a compile being needed.
- **Config:** `wiki_config.py` — optional `features.clippings_sweep_enabled: bool = True`. `config.example.yaml` documents it.
- **Docs:** `AGENTS.md` — short note that `Clippings/` is an inbox-sweep target, not a tracked source folder. Possibly extend `docs/concept.md` "L1 — Working Memory" section.

## Open questions

- **Other Web-Clipper-style folders to sweep?** Some users use `Inbox/` or vault-root for hand-saved markdown. Should this generalize to a configurable list of inbox-folders, each with a target `raw/` subdirectory?
- **Pipeline-time vs hook-time?** Sweep at `flush.py` start (every session-end) is more eager than `compile.py` start (only when daily-log changed + after 18:00). Eager is probably better for clipped articles because the user might want them indexed before the next compile cycle.
- **Move vs copy?** Moving is destructive in the sense that the user loses the "where I clipped to" mental model. Copying creates duplication and downstream "which one is canonical?" confusion. Move is correct, but worth confirming.

## Source

Surfaced during 2026-05-02 vault-status conversation after the engine extraction commit. The triggering question was whether the Obsidian Web Clipper extension's default folder could be redirected into `raw/` — which exposed the missing pipeline coverage of `Clippings/`.
