---
status: ready
---

# Obsidian Plugin — Implementation Plan

## Goal

A desktop Obsidian plugin that surfaces LLM-Wiki workflow queues (pending suggestions, curiosity requests, failed flushes) inside a primary vault, so the user can review/approve/trigger actions without opening a terminal.

Inspired by [istib/obsidian-paperclip](https://github.com/istib/obsidian-paperclip) — same Sidebar-ItemView + Modal + polling pattern, but local filesystem instead of REST.

## Context

- **Primary vault** — user's daily-driver Obsidian vault (PARA-structured personal knowledge).
- **Wiki vault** — separate vault containing `.wiki/`, `raw/`, `knowledge/`, etc. Path is configurable.
- Plugin installs into the **primary vault** and reads the **wiki vault** via `require('fs')` (desktop-only).
- All queue files are plain JSON / YAML on disk — no API, no auth.
- Backend scripts already exist in `<wiki-vault>/.wiki/scripts/` and do all heavy lifting.

## Queues to surface

| Queue | Directory | Format | Action |
|---|---|---|---|
| **Optimization Suggestions** | `<wiki>/raw/suggestions/*.yaml` | YAML with `actions[]` (per-action status) | Approve/Reject per action → runs `execute-suggestions.py --approve FILE N` |
| **Curiosity Requests** | `<wiki>/raw/requests/*.json` | JSON with `status: pending\|processing\|done` | View-only (auto-processed by `follow-requests` piggyback); optional: cancel |
| **Failed Flushes** | `<wiki>/.wiki/scripts/failed-flushes/session-flush-*.md` | Raw markdown transcript | Retry button → `retry-failed-flushes.py` |

## Status widgets (top of sidebar)

- Last flush time (from `.wiki/scripts/last-flush.json`)
- Last compile time + cost (from `.wiki/scripts/state.json`)
- Last piggyback runs (from `.wiki/scripts/piggyback-state.json`)
- Wiki article count (glob `<wiki>/knowledge/**/*.md`)

## Commands (Command Palette)

All commands invoke `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py …` so they work regardless of which directory the plugin spawns from.

- `Wiki: Open Control Panel` — toggles sidebar view
- `Wiki: Run Compile` — `compile.py --max-files <N>`
- `Wiki: Sync Memories` — `sync-memories.py`
- `Wiki: Retry Failed Flushes` — `retry-failed-flushes.py`
- `Wiki: Scan Screenshots` — `scan-screenshots.py --all --limit 50`
- `Wiki: Follow Curiosity Requests` — `scan-email.py --follow-requests`
- `Wiki: Switch Graph View Mode` — rewrites `<vault>/.obsidian/graph.json`

All commands run as detached child processes; stdout surfaces as a `Notice`.

## Settings tab

- **Wiki vault path** — absolute path to the vault holding `.wiki/`
- **Poll interval** (seconds, default 60)
- **Auto-refresh on window focus** (bool, default true)
- **uv path** (default: `uv`)
- **Graph view mode** (dropdown; default `knowledge-only`):
  - `knowledge-only` — `path:knowledge`, `showOrphans: false` (clean wiki graph)
  - `full-vault` — empty search, `showOrphans: true` (everything)
  - `sources-only` — `path:raw OR path:daily` (debug ingest pipeline)
  - `custom` — user-defined search string

  Plugin writes the matching `search` / `showOrphans` / `colorGroups` to `<wiki>/.obsidian/graph.json`.

## Architecture

### Files

```text
obsidian-llm-wiki/
├── manifest.json
├── package.json
├── tsconfig.json
├── esbuild.config.mjs
├── src/
│   ├── main.ts        # plugin bootstrap, commands, settings
│   ├── view.ts        # WikiView (ItemView sidebar)
│   ├── modal.ts       # ItemDetailModal (approve/reject UI)
│   ├── settings.ts    # settings tab + types
│   ├── queues.ts      # file polling, parsing YAML/JSON
│   ├── actions.ts     # script invocations (child_process.spawn)
│   └── status.ts      # reads state files for status widgets
└── styles.css
```

### Data flow

```text
1. Plugin load → start setInterval(POLL_INTERVAL_S * 1000)
2. Timer tick → queues.ts reads filesystem:
   - readdir suggestions/ → parse YAML → filter pending actions
   - readdir requests/ → parse JSON
   - readdir failed-flushes/ → list filenames + mtime
3. State changes (count diff) → Notice "N new <queue>"
4. User clicks item → ItemDetailModal with full payload
5. User clicks Approve/Reject → spawn child_process → execute-suggestions.py
6. On process exit (success) → refresh queues → close modal
```

### Polling strategy

- Compare `JSON.stringify(snapshot)` per queue before/after.
- Re-render the view only when changed.
- Emit `Notice` only when the count increases.

## Implementation phases (~12 h total)

### Phase 1 — Scaffold (2 h)

Clone [obsidian-sample-plugin](https://github.com/obsidianmd/obsidian-sample-plugin), rename, set manifest, add BRAT config for dev install. Verify the sample loads in Obsidian.

### Phase 2 — Settings + queue reader (2 h)

Settings tab + `queues.ts`:
- `loadSuggestions(): Suggestion[]` — readdir + YAML parse (`js-yaml`)
- `loadRequests(): CuriosityRequest[]` — readdir + JSON parse
- `loadFailedFlushes(): FailedFlush[]` — readdir (filename + mtime)

Test against fixture files copied from a real wiki vault.

### Phase 3 — Sidebar view (3 h)

`WikiView extends ItemView`. Header with status widgets, three collapsible queue sections, empty states ("No pending suggestions ✓"), item rows (icon + title + badge with action count). Click row → open modal. Ribbon icon → activate view.

### Phase 4 — Detail modal (2 h)

`ItemDetailModal extends Modal`. Per queue type:
- **Suggestion** — rationale + table of actions with status, Approve/Reject per action
- **Request** — topic, folder, rationale, created timestamp
- **Failed flush** — context preview + Retry button

Button click → `spawn`. Stream stdout into the modal.

### Phase 5 — Commands + actions (2 h)

Register the seven commands above. `actions.ts` wraps `child_process.spawn` with `{ cwd: wikiPath }`. Surface stdout/stderr in `Notice`, debug modal optional.

### Phase 6 — Polling + polish (1 h)

Poll interval, focus refresh, CSS (badges, empty states, hover), error handling (broken YAML, missing files, permission errors), README + install instructions.

## Tech stack

- **TypeScript** (strict mode)
- **Obsidian Plugin API** 1.4+
- **js-yaml** for YAML parsing
- **esbuild** (from sample-plugin template)
- `node:child_process` for spawning Python scripts
- `node:fs/promises` for filesystem reads

## Testing

- **Manual** — install via BRAT, open sidebar, verify queues populate, click item, approve, verify on-disk change.
- **Fixtures** — copy real `raw/suggestions/*.yaml` and `raw/requests/*.json` into a test vault.
- **No unit tests initially** — this is a thin UI layer; the backend is exercised by the Python scripts directly.

## Out of scope (v1)

- Mobile support (desktop-only due to `require('fs')`)
- Drag-drop kanban
- Inline agent chat
- AI integration inside the plugin (the wiki itself has that)
- Cross-platform path translation
- Telemetry / metrics

## Success criteria

1. Sidebar shows three queues with live counts.
2. Click pending suggestion → modal with actions → approve → YAML updated → action executes → file change.
3. `Notice` fires when items appear.
4. All commands work from the palette.
5. Status widgets show accurate "last run" times.
