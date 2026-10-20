# llm-wiki Desktop

A macOS **menu-bar app** for llm-wiki — the GUI alternative to the `wiki` CLI. No dock
icon: the brain icon in the menu bar opens a panel, and the panel opens the windows.

## What you see

**Panel** (click the icon)

- **Ask** — a question to your library, answered in a few lines (`wiki query --brief`);
  wikilink chips open the notes.
- **Library · Health · Capture** — note count with a 14-day sparkline; a health ring with
  the doctor's checks one click away; the recording state with its **Pause / Resume**
  button (red dot = recording).
- **Next up** — one list of what the engine wants from you, each row with its verb
  (`wiki menu --json` + `wiki doctor --json`); a running row shows progress, a finished
  row keeps its result pill.
- **Recent** — the latest notes, a dot on the ones you have not seen yet.
- Footer — **+ Save a web page**, **Sources**, **Tools** (the engine's read-only checks),
  **Quit**. Header — **Overview / Notes / Inbox**, the **Library** pill (opens the vault
  in Obsidian), **Settings**.

**Windows**

- **Overview** — notes updated per day (30 days), notes by type, capture over the last
  24 h, health, next up; every chart has a table twin.
- **Notes** — filter your notes by title, open one.
- **Inbox** — captures waiting for a decision, grouped by source: Keep or Dismiss.
- **Settings** — open in Obsidian, start at login, file access, screen & audio capture.
- **Welcome** — first run: what is recorded, where to pause it, where the vault lives.

## Install

1. Build the DMG (below) or get `llm-wiki-<version>-arm64.dmg` from someone who did.
2. Open it, drag **llm-wiki** into **Applications**.
3. Unsigned build: macOS blocks the first double-click — **right-click → Open → Open**,
   once. A signed build (below) skips this.

## File access (first run)

If the panel says it can't read your library (0 notes): the vault usually lives under
iCloud Drive, which an app launched from Finder cannot read until you grant it.
**System Settings → Privacy & Security → Full Disk Access → add llm-wiki**, then reopen
the app. Settings → **File access → Open System Settings** jumps there. `npm start`
inherits the terminal's permissions and needs none.

## Start at login

Settings → **Start at login** writes a per-user LaunchAgent
(`~/Library/LaunchAgents/cloud.yesterday.llm-wiki.plist`, `RunAtLoad` → `open` the app) —
reliable for an unsigned app, unlike Electron's `setLoginItemSettings`. Unchecking removes
it. Installed app only, not `npm start`.

## Dev

```bash
npm ci
npm start                    # vite + electron
npm test                     # tsc --noEmit + svelte-check + vitest
npm run test:panel           # real Electron: dismiss/reopen the panel, then Quit (requires a desktop)
npm run lint                 # biome check   (from Claude Code: rtk proxy npm run lint)
npm run shots                # every window × light/dark × state → out/shots/ + report.json
npm run reinstall            # build the .app, install over /Applications/llm-wiki.app, relaunch
LLM_WIKI_DEBUG=1 npm start   # verbose IPC logging
```

`npm run shots` is the gate before a UI change is called done: every page is strict
(overlapping or clipped text fails the run), the panel at rest must fit the 640 px
popover, and `out/shots/report.json` carries heights, content heights and page errors.
`npm run reinstall` is the loop for what only the installed app shows (file access, login
item); an unsigned app's Full Disk Access grant is keyed on its code hash and may need
re-granting after a rebuild.

Closing the panel dismisses it; the tray icon and ⌥-Space can open it again. Use **Quit**
to exit the app. `test:panel` exercises this lifecycle with a disposable HOME and userData,
without using the operator's vault or changing the capture daemon.

The engine's `--json` payloads are a typed contract: `docs/contracts/{menu,doctor}.schema.json`
(generated from `scripts/core/contracts.py`). `src/lib/contract.test.ts` validates the
engine's golden output against them with ajv and runs it through `parseMenu` /
`parseDoctor`. The representative fixtures in `src/vault/*.test.ts` validate too, and a
field-inventory test fails when the engine adds a field the app has not decided about.

Layout: `src/main.ts` (main process: tray, windows, IPC) · `src/preload.ts` ·
`src/vault/` (the engine seam — every `wiki` call goes through `wiki-exec.ts:runWiki` and
the engine's `--json` seams) · `src/listeners/` (screenpipe status + hourly timeline) ·
`src/lib/` (action model, activity derivations) · `src/ui/` (primitives: Button, Switch,
TypeBadge, Ring, Sparkline, Columns, HBars, HeatStrip, DataTable) ·
`src/styles/tokens.css` (the design tokens — the only place colours, scales and motion
live) · `src/windows/<name>/` (one Svelte app per window) · `scripts/shots/` (harness,
fixtures, audit + gates).

## Build

```bash
npm run dmg          # .dmg only → out/make/dmg/<arch>/llm-wiki-<version>-<arch>.dmg
npm run make         # .dmg + .zip
npm run package      # .app only (no installer)
```

### Signed + notarized build (runbook)

What makes the app installable without the right-click dance and keeps the Full Disk
Access grant across updates. Needs an **Apple Developer account** ($99/yr).
`forge.config.ts` signs + notarizes when the env vars are present and does nothing
without them.

1. **Enroll** at developer.apple.com (Apple Developer Program).
2. **Create a "Developer ID Application" certificate** (Xcode → Settings → Accounts →
   Manage Certificates → +). Verify: `security find-identity -v -p codesigning` lists it.
3. **App-specific password**: appleid.apple.com → Sign-In & Security → App-Specific
   Passwords.
4. **Team ID**: developer.apple.com → Membership (10 characters).
5. **Build:**
   ```bash
   export APPLE_ID="you@example.com"
   export APPLE_PASSWORD="abcd-efgh-ijkl-mnop"   # the app-specific password
   export APPLE_TEAM_ID="AB12CD34EF"
   npm run dmg
   ```
   Notarization adds a few minutes. No entitlements file is needed —
   `@electron/osx-sign` supplies the Electron defaults (incl. JIT).
6. **Verify:** `spctl -a -vvv -t install out/make/dmg/*/llm-wiki-*.dmg` →
   `accepted / Notarized Developer ID`.

### Auto-update (after signing)

Squirrel.Mac refuses to update unsigned apps, so auto-update waits for signing plus a
release host (e.g. GitHub Releases); then wire `update-electron-app` against the feed.
Until then: distribute the signed DMG, reinstall by hand.

## Notes

- Vault discovery uses the engine registry `~/.config/llm-wiki/vaults`.
- Bundle id `cloud.yesterday.llm-wiki` (`forge.config.ts`).
- Listener and vault status are read from the filesystem; everything that acts shells
  out to the `wiki` engine through the one runner.
