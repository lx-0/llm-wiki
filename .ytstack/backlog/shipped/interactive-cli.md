# Interactive, context-sensitive `wiki` CLI

**Status:** concept (Phase 1, llm-wiki-change)
**Date:** 2026-05-17

## Problem

The `wiki` CLI has 33 subcommands. The current `top_menu()` (entered by typing
bare `wiki`) only exposes 6 setup-flavored actions (status / setup / config /
hooks install/uninstall / update). All 27 daily-driver commands (compile,
flush, query, lint, collect, ingest-*, correct, take, dream, curiosity,
suggestions, pin, review-wiki, process-inbox, …) require recall from memory
plus `wiki <cmd> --help` to remember flags.

Operator self-report: "ich kann mir die ganzen wiki befehle nicht merken".

## Goal

Typing bare `wiki` lands the operator on a **home screen** that:

1. Surfaces **what's actionable RIGHT NOW** in the vault (ranked, one-key shortcuts).
2. Falls back to a **browse-by-category** menu for everything else.
3. Stays **fast** (sub-200ms first paint — context probe must not block).
4. Stays **dep-free** (no new system binaries like `gum` / `fzf`; reuse `lib/ui.sh`).

## Shape (concrete sketch)

```
$ wiki

  wiki — lxw vault (commit f9b02c5)

  ▸ Pending in your vault
      1) 3 files in inbox/                  → process-inbox
      2) 12 sources changed since compile   → compile
      3) 2 curiosity requests pending       → curiosity --run-oldest
      4) 5 entities overdue for dream       → dream --all-entities

  ▸ Quick actions
      q) query     f) flush      l) lint     s) status

  ▸ Browse
      c) collectors    i) ingest    k) knowledge ops    g) setup    a) all

  ▸ Other
      h) help     x) exit

  Pick one (1-4 / q,f,l,s,c,i,k,g,a,h,x):
```

- Numbers run the suggested command directly.
- Letters route to category sub-menus (existing `select_one` pattern).
- Category sub-menus list every command in that group with a one-line
  description + arg-prompt helper that calls the existing `cmd_*` dispatcher.

## Context signals (Phase 1 set)

A small Python probe (`scripts/menu_context.py`) outputs a JSON array of
suggestions in priority order. Cheap I/O only — no LLM, no network, no compile
state walks beyond `os.listdir`. Hard timeout 500ms; on timeout the menu just
omits suggestions and renders the browse section.

| Signal                                              | Command                       | Priority |
|-----------------------------------------------------|-------------------------------|----------|
| `<vault>/inbox/` non-empty                          | `process-inbox`               | 1        |
| Sources newer than last `compile.log`               | `compile`                     | 2        |
| `raw/requests/*.md` with `status: pending`          | `curiosity --run-oldest`      | 3        |
| `raw/suggestions/*.yaml` with approved-not-executed | `suggestions`                 | 4        |
| Entities past dream cooldown                        | `dream --all-entities`        | 5        |
| `daily/sessions/YYYY-MM-DD.md` missing for today    | `flush`                       | 6        |
| Lint cache older than newest compile output         | `lint --structural-only`      | 7        |

Each row only renders if its count > 0. Caps at top 5 visible — rest live
under `a) all suggestions`.

## Categories (Phase 1)

Six category sub-menus, each mapping to existing `cmd_*` functions:

- **collectors** — `collect --list`, `collect <name>`, OAuth bootstraps
- **ingest** — `process-inbox`, `ingest-html`, `ingest-youtube`
- **knowledge ops** — `compile`, `lint`, `query`, `review-wiki`, `dream`, `dream-entity`, `pin`
- **facts** — `correct add/list/edit/remove/apply`, `take add/list/show/remove`
- **automation** — `curiosity`, `suggestions`, `flush`, `agent`
- **setup** — `setup`, `config`, `hooks`, `skills`, `update`, `seed`, `status`, `version`

`a) all` is the flat list (current `wiki help` content, but as a picker).

## Integration with existing code

- New entry-point function `home_screen()` in `wiki` (replaces `top_menu()`).
- New `category_menu <name>` helper that wraps `select_one` over a static map.
- New `arg_prompt <cmd>` helper that asks for required positional args (e.g.
  `wiki pin <article>` prompts for article name with fzf-style completion
  over `find knowledge/ -name '*.md'`).
- New `scripts/menu_context.py` — pure Python, reads vault state, emits JSON.
- `wiki help` keeps existing comment-block dump (non-interactive form unchanged).
- All existing `wiki <subcommand>` invocations continue to work unchanged.

## What stays out (deferred)

- **Fuzzy command picker** (`gum filter` / `fzf` integration) — new system
  dep, parking until operator hits the wall of the category menu.
- **LLM-driven suggestions** ("you've been editing X, want to compile?") —
  context probe must stay free + sub-500ms.
- **Persistent menu state** (last-picked, history) — premature.
- **TUI framework** (textual, gum) — bash + ANSI is sufficient for this scope.
- **Auto-arg-completion via fzf** — start with simple `read -p` prompts,
  add completion only if it hurts.

## Edge cases / failure modes

- **Context probe slow or crashes** → menu renders without suggestions
  section, logs warning. Never blocks home screen.
- **TTY missing** (script invocation, CI) → bare `wiki` prints
  non-interactive help (current `cmd_help` output) and exits 0, like before.
- **Empty vault** (fresh install, no inbox / sources / state) → suggestions
  section auto-hides, prompts to run `wiki setup`.
- **Vault path detection** — `WIKI_DIR` + `ROOT_DIR` already resolved in
  the bash entry-point; pass them into menu_context.py via env vars.
- **One-key collisions** — number keys for suggestions (1-5), letters for
  categories (q/f/l/s/c/i/k/f/a/h/x). Curated to avoid double-bind.

## Out-of-scope-but-related

- Cheatsheet improvement of `wiki help` itself (grouped table view) — could
  ride along in the same PR since the category map is reusable.

## Resolved decisions (operator review 2026-05-17)

1. **Signal set:** 7 signals as listed in the table above (inbox / compile /
   curiosity / suggestions / dream / flush / lint). No `correct` / `take`
   overdue checks in v1.
2. **Categories:** 6 buckets as listed (collectors / ingest / knowledge-ops
   / facts / automation / setup).
3. **Navigation:** Numeric/arrow input AS WELL AS letter shortcuts. Letters
   shown inline as `[q] query`; numbers/arrows steer; letters jump.
4. **Entry point:** bare `wiki` becomes the new home screen WHEN stdin is
   a TTY. `wiki menu` added as explicit alias (same function). All
   existing `wiki <subcommand>` invocations stay 100% scriptable —
   non-TTY (`wiki` piped, in a CI, via hook) falls back to printing
   `cmd_help` and exiting 0 like before.
