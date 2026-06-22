# llm-wiki Desktop

A macOS **menubar app** for llm-wiki — a GUI alternative to the `wiki` CLI for
technical and non-technical users. Lives in the menubar (no dock icon): the brain
icon shows status at a glance, and clicking it opens a panel to control the
screenpipe listener, see vault status, update knowledge (`wiki compile`), and open
the vault in Obsidian.

## Install (end user)

1. **Build the DMG** (see Build below) or get `llm-wiki.dmg` from someone who did.
2. Open the DMG, drag **llm-wiki** into **Applications**.
3. **First launch** (unsigned build only): the app isn't notarized yet, so macOS
   Gatekeeper blocks a normal double-click. **Right-click the app → Open → Open**
   (only needed once). A signed/notarized build (below) skips this.
4. The **brain icon** appears in the menubar. Click it for the panel.

## Start at login (autostart)

The app registers itself — no System Settings fiddling:

> **Right-click the menubar brain icon → check “Start at login”.**

This calls macOS's login-item API (`app.setLoginItemSettings`). Un-check it the
same way. The same right-click menu also has **Quit llm-wiki**.

(There is no separate LaunchAgent — unlike the screenpipe capture daemon, this is
a normal GUI login item the app manages itself.)

## Use

- **Left-click** the menubar icon → panel (status, controls).
- **`●` / `◍`** next to the icon = recording on / system-audio stalled. No glyph = stopped.
- **Start / Stop** → toggles the screenpipe listener.
- **Update** → runs `wiki compile` (refreshes knowledge from new material), with
  live `x of y` progress.
- **vault pill (e.g. `lxw ↗`)** → opens the vault in Obsidian.

## Dev

```bash
npm install
npm start          # run in dev (vite + electron)
npm test           # vitest unit tests
LLM_WIKI_DEBUG=1 npm start   # verbose IPC logging
```

## Build

```bash
npm run dmg        # build the .dmg only        → out/make/llm-wiki-*.dmg
npm run make       # build .dmg + .zip
npm run package    # build the .app only (no installer)
```

### Signed + notarized build (for distribution without Gatekeeper warnings)

Set your Apple Developer ID env vars, then build — `forge.config.ts` signs +
notarizes automatically when these are present:

```bash
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="app-specific-password"   # from appleid.apple.com
export APPLE_TEAM_ID="XXXXXXXXXX"
npm run dmg
```

A “Developer ID Application” certificate must be in your login keychain.

## Notes

- Vault discovery uses the engine registry `~/.config/llm-wiki/vaults`.
- App bundle id: `cloud.yesterday.llm-wiki` (in `forge.config.ts`) — rename to your
  org convention if desired.
- The app reads listener/vault status straight from the filesystem (launchd +
  the vault); only `Update` (compile) shells out to the `wiki` engine.
