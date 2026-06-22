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

## Grant file access (first run, important)

If the vault shows **“Can't read your vault” / 0 notes**, the app lacks macOS file
access. The vault usually lives under **iCloud Drive**, which a Finder-launched app
can't read until you grant it:

> **System Settings → Privacy & Security → Full Disk Access → add `llm-wiki`** (toggle on),
> then reopen the app.

(The panel's “Open Settings” button jumps you straight there.) This is the same
kind of macOS permission the screenpipe capture needs — a fresh `.app` has no file
access until granted. Running in dev (`npm start`) works without it because it
inherits the terminal's permissions.

## Start at login (autostart) + Quit

Both live in the **panel footer** (open the panel by clicking the menubar icon):

> **☐ Start at login** — check it to launch the app at login.
> **Quit** — quit the app.

"Start at login" writes a per-user **LaunchAgent**
(`~/Library/LaunchAgents/cloud.yesterday.llm-wiki.plist`, `RunAtLoad` → `open` the
app) — this is reliable and works for the unsigned app, unlike Electron's
`setLoginItemSettings` (which doesn't register for unsigned apps on modern macOS).
Un-checking removes the plist. Only works in the **installed** app (the LaunchAgent
points at the app bundle), not `npm start` dev. A tray right-click menu was dropped
— unreliable for macOS menubar apps.

## Use

- **Left-click** the menubar icon → panel.
- **Ask your wiki** → type a question, get a short answer (wraps `wiki query --brief`).
- **What's pending** → the engine's own prioritized to-do list (`wiki menu --json`):
  entities overdue for synthesis, edits since the last lint, scan requests to
  review… each with a one-tap **Run**.
- **`●` / `◍`** next to the icon = recording on / system-audio stalled. No glyph = stopped.
- **Start / Stop** → toggles the screenpipe listener.
- **Update knowledge** → turns newly captured material (notes, voice, screenshots,
  meetings) into wiki articles — runs `wiki compile`, with live `x of y` progress.
- **Health** → `● Everything healthy` / `⚠ N issues` (from `wiki doctor`), plus an
  **Update app** button when an engine update is available.
- **vault pill (e.g. `lxw ↗`)** → opens the vault in Obsidian.
- **Advanced** (collapsed) → Check for problems / Check links / Find duplicates /
  Review quality — all read-only / $0.

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
