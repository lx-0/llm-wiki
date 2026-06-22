// Autostart via a per-user LaunchAgent — reliable and signing-independent, unlike
// Electron's app.setLoginItemSettings (which doesn't register for unsigned apps on
// modern macOS via SMAppService). Toggling writes/removes a plist that `open`s the
// app bundle at login (RunAtLoad). File-based ⇒ testable (the plist's presence IS
// the state). No KeepAlive — autostart only, not respawn-on-quit.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { app } from 'electron';

export const AUTOSTART_LABEL = 'cloud.yesterday.llm-wiki';

export function plistPath(): string {
  return path.join(os.homedir(), 'Library', 'LaunchAgents', `${AUTOSTART_LABEL}.plist`);
}

/** `.../llm-wiki.app/Contents/MacOS/llm-wiki` → `.../llm-wiki.app` (pure). */
export function appBundlePath(exe: string): string {
  const marker = '.app/';
  const i = exe.indexOf(marker);
  return i >= 0 ? exe.slice(0, i + marker.length - 1) : exe;
}

/** LaunchAgent plist that opens the app bundle at login (pure). */
export function buildPlist(bundlePath: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${AUTOSTART_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>${bundlePath}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
`;
}

export function isAutostartEnabled(): boolean {
  return fs.existsSync(plistPath());
}

/** Enable/disable autostart; returns the resulting state. */
export function setAutostart(enable: boolean): boolean {
  const p = plistPath();
  if (enable) {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, buildPlist(appBundlePath(app.getPath('exe'))));
  } else {
    try {
      fs.unlinkSync(p);
    } catch {
      /* not present */
    }
  }
  return isAutostartEnabled();
}
