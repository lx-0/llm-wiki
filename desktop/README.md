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

Open the panel (click the menubar icon):

> **☐ Start at login** — under the collapsible **Settings** section; check it to launch the app at login.
> **Quit** — in the footer.

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
npm run reinstall  # build the .app + (re)install into /Applications + launch
```

`npm run reinstall` (`scripts/dev-install.sh`) is the fast local-test loop: it
builds just the `.app`, rsyncs it over `/Applications/llm-wiki.app` (quitting the
running copy first), and relaunches — no DMG mount/drag. Use this to test the
**installed** app (TCC / login-item behave for real, unlike `npm start`). Caveat:
an unsigned app's Full-Disk-Access grant is keyed on its code hash and may need
re-granting after a rebuild.

## Build

```bash
npm run dmg        # build the .dmg only        → out/make/llm-wiki-*.dmg
npm run make       # build .dmg + .zip
npm run package    # build the .app only (no installer)
```

### Signed + notarized build (runbook — for distribution without Gatekeeper warnings)

This is what makes the app installable by non-technical users (no right-click→Open)
and makes the Full-Disk-Access grant persist across updates. One-time setup needs an
**Apple Developer account** ($99/yr). `forge.config.ts` is already wired — it signs +
notarizes automatically when the env vars are present, and does nothing without them.

1. **Enroll** at developer.apple.com (Apple Developer Program).
2. **Create a “Developer ID Application” certificate** (Xcode → Settings → Accounts →
   Manage Certificates → +, or the Developer portal) — it lands in your login keychain.
   Verify: `security find-identity -v -p codesigning` shows `Developer ID Application: …`.
3. **App-specific password** for notarization: appleid.apple.com → Sign-In & Security →
   App-Specific Passwords → generate one.
4. **Find your Team ID**: developer.apple.com → Membership (10-char, e.g. `AB12CD34EF`).
5. **Build signed + notarized:**
   ```bash
   export APPLE_ID="you@example.com"
   export APPLE_PASSWORD="abcd-efgh-ijkl-mnop"   # the app-specific password
   export APPLE_TEAM_ID="AB12CD34EF"
   npm run dmg
   ```
   Notarization adds a few minutes (Apple processes it server-side). No entitlements
   file is needed — `@electron/osx-sign` supplies the Electron defaults (incl. JIT).
6. **Verify** the result: `spctl -a -vvv -t install out/make/llm-wiki-*.dmg` →
   `accepted / Notarized Developer ID`.

### Auto-update (after signing)

Auto-update needs a **signed** app (Squirrel.Mac refuses to update unsigned apps) +
a release host (e.g. GitHub Releases). Once signing is in place, wire
`update-electron-app` against a releases feed — deferred until the release host is
chosen. Until then, distribute the signed DMG and reinstall manually.

## Notes

- Vault discovery uses the engine registry `~/.config/llm-wiki/vaults`.
- App bundle id: `cloud.yesterday.llm-wiki` (in `forge.config.ts`) — rename to your
  org convention if desired.
- The app reads listener/vault status straight from the filesystem (launchd +
  the vault); only `Update` (compile) shells out to the `wiki` engine.
