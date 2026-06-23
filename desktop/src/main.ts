import { app, BrowserWindow, ipcMain, Tray, nativeImage, shell, globalShortcut, Notification } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';
import { LISTENERS, getListener } from './listeners/registry';
import { getListenerStatus } from './listeners/status';
import { startListener, stopListener, restartListener, type LifecycleAction, type LifecycleResult } from './listeners/lifecycle';
import { LISTENER_STATUS_CHANNEL, LISTENER_CONTROL_CHANNEL } from './listeners/ipc';
import { getVaultStatus, listEntries, previewEntry } from './vault/status';
import { resolveVault } from './vault/registry';
import {
  startCompile,
  isCompiling,
  currentProgress,
  startEngineCommand,
  startEngineArgs,
  runningCommand,
  type EngineCommandId,
} from './vault/compile';
import { getDoctor } from './vault/doctor';
import { runQuery } from './vault/query';
import { getMenu } from './vault/menu';
import { listCollectors } from './vault/collectors';
import { listTriage, triageAction } from './vault/triage';
import {
  VAULT_STATUS_CHANNEL,
  VAULT_LIST_CHANNEL,
  VAULT_PREVIEW_CHANNEL,
  VAULT_COLLECTORS_CHANNEL,
  VAULT_TRIAGE_CHANNEL,
  VAULT_TRIAGE_ACTION_CHANNEL,
  VAULT_COMPILE_CHANNEL,
  VAULT_COMPILE_STATUS_CHANNEL,
  VAULT_COMPILE_PROGRESS_CHANNEL,
  VAULT_COMPILE_DONE_CHANNEL,
  VAULT_OPEN_OBSIDIAN_CHANNEL,
  VAULT_OPEN_FILE_CHANNEL,
  VAULT_OPEN_FDA_CHANNEL,
  VAULT_DOCTOR_CHANNEL,
  VAULT_MENU_CHANNEL,
  VAULT_QUERY_CHANNEL,
  VAULT_RUN_CHANNEL,
  VAULT_RUN_ARGS_CHANNEL,
  VAULT_RUN_STATUS_CHANNEL,
  VAULT_RUN_PROGRESS_CHANNEL,
  VAULT_RUN_DONE_CHANNEL,
} from './vault/ipc';
import { BRAIN_PNG_1X, BRAIN_PNG_2X } from './assets/brainIcon';
import { PANEL_VISIBILITY_CHANNEL, PANEL_RESIZE_CHANNEL } from './panel/ipc';
import {
  APP_LOGIN_GET_CHANNEL,
  APP_LOGIN_SET_CHANNEL,
  APP_QUIT_CHANNEL,
  APP_OPEN_SETTINGS_CHANNEL,
  APP_OPEN_BROWSE_CHANNEL,
  APP_OPEN_COCKPIT_CHANNEL,
  APP_CLOSE_COCKPIT_CHANNEL,
  APP_OPEN_ATLAS_CHANNEL,
  APP_OPEN_TRIAGE_CHANNEL,
  APP_ONBOARDING_DONE_CHANNEL,
} from './app/ipc';
import fs from 'node:fs';
import { isAutostartEnabled, setAutostart } from './app/autostart';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

// Verbose IPC logging only when explicitly enabled (LLM_WIKI_DEBUG=1) — otherwise
// a background app would spam the console on every poll.
const DEBUG = process.env.LLM_WIKI_DEBUG === '1';

// Menubar badge — count of the engine's pending "what's pending" items.
let pendingCount = 0;
function updateTrayTitle(): void {
  if (!tray) return;
  tray.setTitle(`${trayGlyph()}${pendingCount > 0 ? ` ${pendingCount}` : ''}`);
}
async function refreshBadge(): Promise<void> {
  const m = await getMenu();
  pendingCount = m ? m.suggestions.length : 0;
  updateTrayTitle();
}

// Native notification when a background job finishes and the panel isn't open
// (so a long compile/dream doesn't need babysitting).
function notifyDone(body: string): void {
  if (panel?.isVisible() || !Notification.isSupported()) return;
  new Notification({ title: 'llm-wiki', body, silent: true }).show();
}

// IPC: listener status (system data — launchd + sqlite, read directly; no engine call).
ipcMain.handle(LISTENER_STATUS_CHANNEL, () => {
  const all = LISTENERS.map((l) => getListenerStatus(l));
  if (DEBUG) console.log(`${LISTENER_STATUS_CHANNEL} -> ${JSON.stringify(all)}`);
  return all;
});

// IPC: listener control (start/stop/restart). Renderer input is validated here.
const ACTIONS: Record<LifecycleAction, (def: ReturnType<typeof getListener> & object) => LifecycleResult> = {
  start: startListener,
  stop: stopListener,
  restart: restartListener,
};
ipcMain.handle(LISTENER_CONTROL_CHANNEL, (_e, id: string, action: LifecycleAction): LifecycleResult => {
  const def = getListener(id);
  if (!def) return { action, ok: false, error: `unknown listener: ${id}` };
  const fn = ACTIONS[action];
  if (!fn) return { action, ok: false, error: `unknown action: ${action}` };
  const res = fn(def);
  if (DEBUG) console.log(`${LISTENER_CONTROL_CHANNEL} ${id}/${action} -> ${JSON.stringify(res)}`);
  // refresh the menubar glyph promptly after a toggle
  tray?.setTitle(trayGlyph());
  return res;
});

// IPC: vault status (filesystem-derived facts about the active vault; no engine call).
ipcMain.handle(VAULT_STATUS_CHANNEL, () => {
  const v = getVaultStatus();
  if (DEBUG) console.log(`${VAULT_STATUS_CHANNEL} -> ${JSON.stringify(v)}`);
  return v;
});

// IPC: compile (engine action — long-running). Starts the process and pushes the
// result to the panel when it finishes.
ipcMain.handle(VAULT_COMPILE_CHANNEL, () => {
  return startCompile(
    (progress) => panel?.webContents.send(VAULT_COMPILE_PROGRESS_CHANNEL, progress),
    (result) => {
      if (DEBUG) console.log(`${VAULT_COMPILE_DONE_CHANNEL} -> ${JSON.stringify(result)}`);
      panel?.webContents.send(VAULT_COMPILE_DONE_CHANNEL, result);
      notifyDone(result.ok ? 'Knowledge updated.' : 'Update failed.');
      void refreshBadge();
    },
  );
});
ipcMain.handle(VAULT_COMPILE_STATUS_CHANNEL, () => ({ running: isCompiling(), progress: currentProgress() }));

// IPC: app-level — autostart (LaunchAgent) + quit (surfaced in the panel footer).
ipcMain.handle(APP_LOGIN_GET_CHANNEL, () => isAutostartEnabled());
ipcMain.handle(APP_LOGIN_SET_CHANNEL, (_e, open: boolean) => setAutostart(open));
ipcMain.on(APP_QUIT_CHANNEL, () => app.quit());
ipcMain.on(APP_OPEN_SETTINGS_CHANNEL, () => openSettings());
ipcMain.on(APP_OPEN_BROWSE_CHANNEL, () => openBrowse());

// Browse window (browse.html) — a searchable list of all knowledge entries.
let browseWin: BrowserWindow | null = null;
function openBrowse(): void {
  if (browseWin && !browseWin.isDestroyed()) {
    browseWin.show();
    browseWin.focus();
    return;
  }
  browseWin = new BrowserWindow({
    width: 480,
    height: 620,
    minWidth: 360,
    minHeight: 400,
    title: 'Browse — llm-wiki',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  browseWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    browseWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/browse.html`);
  } else {
    browseWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/browse.html`));
  }
  browseWin.on('closed', () => {
    browseWin = null;
  });
}

// Cockpit window (cockpit.html) — full-window neural-net view, toggle of compact.
ipcMain.on(APP_OPEN_COCKPIT_CHANNEL, () => openCockpit());
ipcMain.on(APP_CLOSE_COCKPIT_CHANNEL, () => cockpitWin?.close());
let cockpitWin: BrowserWindow | null = null;
function openCockpit(): void {
  if (cockpitWin && !cockpitWin.isDestroyed()) {
    cockpitWin.show();
    cockpitWin.focus();
    return;
  }
  cockpitWin = new BrowserWindow({
    width: 1040,
    height: 700,
    minWidth: 720,
    minHeight: 520,
    title: 'llm-wiki — Cockpit',
    backgroundColor: '#0b1220',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  cockpitWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    cockpitWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/cockpit.html`);
  } else {
    cockpitWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/cockpit.html`));
  }
  cockpitWin.on('closed', () => {
    cockpitWin = null;
  });
}

// Atlas window (atlas.html) — hierarchical knowledge-graph view.
ipcMain.on(APP_OPEN_ATLAS_CHANNEL, () => openAtlas());
let atlasWin: BrowserWindow | null = null;
function openAtlas(): void {
  if (atlasWin && !atlasWin.isDestroyed()) {
    atlasWin.show();
    atlasWin.focus();
    return;
  }
  atlasWin = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 760,
    minHeight: 520,
    title: 'llm-wiki — Atlas',
    backgroundColor: '#0b1220',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  atlasWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    atlasWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/atlas.html`);
  } else {
    atlasWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/atlas.html`));
  }
  atlasWin.on('closed', () => {
    atlasWin = null;
  });
}

// Triage — the intent-inbox review window (per-item accept/dismiss).
let triageWin: BrowserWindow | null = null;
function openTriage(): void {
  if (triageWin && !triageWin.isDestroyed()) {
    triageWin.show();
    triageWin.focus();
    return;
  }
  triageWin = new BrowserWindow({
    width: 720,
    height: 760,
    minWidth: 480,
    minHeight: 420,
    title: 'llm-wiki — Triage',
    backgroundColor: '#0b1220',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  triageWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    triageWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/triage.html`);
  } else {
    triageWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/triage.html`));
  }
  triageWin.on('closed', () => {
    triageWin = null;
  });
}
ipcMain.on(APP_OPEN_TRIAGE_CHANNEL, () => openTriage());

// Settings lives in its own window (settings.html), opened from the header gear.
let settingsWin: BrowserWindow | null = null;
function openSettings(): void {
  if (settingsWin && !settingsWin.isDestroyed()) {
    settingsWin.show();
    settingsWin.focus();
    return;
  }
  settingsWin = new BrowserWindow({
    width: 380,
    height: 250,
    resizable: false,
    fullscreenable: false,
    minimizable: false,
    maximizable: false,
    title: 'llm-wiki Settings',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  settingsWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    settingsWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/settings.html`);
  } else {
    settingsWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/settings.html`));
  }
  settingsWin.on('closed', () => {
    settingsWin = null;
  });
}

// First-run onboarding — a flag file in userData marks completion.
function onboardedFlag(): string {
  return path.join(app.getPath('userData'), 'onboarded');
}
function hasOnboarded(): boolean {
  return fs.existsSync(onboardedFlag());
}
let onboardingWin: BrowserWindow | null = null;
function openOnboarding(): void {
  if (onboardingWin && !onboardingWin.isDestroyed()) {
    onboardingWin.show();
    onboardingWin.focus();
    return;
  }
  onboardingWin = new BrowserWindow({
    width: 460,
    height: 580,
    resizable: false,
    fullscreenable: false,
    maximizable: false,
    title: 'Welcome to llm-wiki',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  onboardingWin.setMenuBarVisibility(false);
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    onboardingWin.loadURL(`${MAIN_WINDOW_VITE_DEV_SERVER_URL}/onboarding.html`);
  } else {
    onboardingWin.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/onboarding.html`));
  }
  onboardingWin.on('closed', () => {
    onboardingWin = null;
  });
}
ipcMain.on(APP_ONBOARDING_DONE_CHANNEL, () => {
  try {
    fs.writeFileSync(onboardedFlag(), new Date().toISOString());
  } catch {
    /* best-effort */
  }
  onboardingWin?.close();
});

// IPC: open the vault in Obsidian (the reading/browsing surface for non-techies).
ipcMain.handle(VAULT_OPEN_OBSIDIAN_CHANNEL, () => {
  const v = resolveVault();
  if (!v) return { ok: false };
  void shell.openExternal(`obsidian://open?vault=${encodeURIComponent(v.name)}`);
  return { ok: true };
});
ipcMain.on(VAULT_OPEN_FILE_CHANNEL, (_e, file: string) => {
  const v = resolveVault();
  if (!v) return;
  void shell.openExternal(
    `obsidian://open?vault=${encodeURIComponent(v.name)}&file=${encodeURIComponent(file)}`,
  );
});
ipcMain.on(VAULT_OPEN_FDA_CHANNEL, () => {
  void shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles');
});

// IPC: all knowledge entries (for the Browse window) — system data, fs read.
ipcMain.handle(VAULT_LIST_CHANNEL, () => listEntries());
ipcMain.handle(VAULT_PREVIEW_CHANNEL, (_e, file: string) => previewEntry(file));
ipcMain.handle(VAULT_COLLECTORS_CHANNEL, () => listCollectors());
ipcMain.handle(VAULT_TRIAGE_CHANNEL, (_e, showAll: boolean) => listTriage(showAll));
ipcMain.handle(VAULT_TRIAGE_ACTION_CHANNEL, (_e, stem: string, action: 'accept' | 'dismiss') => triageAction(stem, action));

// IPC: doctor (health + update-available) — one read-only call.
ipcMain.handle(VAULT_DOCTOR_CHANNEL, () => getDoctor());

// IPC: the engine's actionable menu (what's pending) + ask the knowledge base.
ipcMain.handle(VAULT_MENU_CHANNEL, () => getMenu());
ipcMain.handle(VAULT_QUERY_CHANNEL, (_e, question: string) => runQuery(question));

// IPC: run a generic engine command (update / lint / links / dedup / review).
ipcMain.handle(VAULT_RUN_CHANNEL, (_e, id: EngineCommandId) => {
  return startEngineCommand(
    id,
    (progress) => panel?.webContents.send(VAULT_RUN_PROGRESS_CHANNEL, { id, progress }),
    (result) => {
      if (DEBUG) console.log(`${VAULT_RUN_DONE_CHANNEL} ${id} -> ${JSON.stringify(result)}`);
      panel?.webContents.send(VAULT_RUN_DONE_CHANNEL, { id, result });
      notifyDone(result.ok ? `${id} finished.` : `${id} failed.`);
      void refreshBadge();
    },
  );
});
// IPC: run an arbitrary menu-suggestion command (cmd string → args).
ipcMain.handle(VAULT_RUN_ARGS_CHANNEL, (_e, args: string[]) => {
  const id = args.join(' ');
  return startEngineArgs(
    args,
    (progress) => panel?.webContents.send(VAULT_RUN_PROGRESS_CHANNEL, { id, progress }),
    (result) => {
      if (DEBUG) console.log(`${VAULT_RUN_DONE_CHANNEL} ${id} -> ${JSON.stringify(result)}`);
      panel?.webContents.send(VAULT_RUN_DONE_CHANNEL, { id, result });
      notifyDone(result.ok ? 'Finished.' : 'A task failed.');
      void refreshBadge();
    },
  );
});
ipcMain.handle(VAULT_RUN_STATUS_CHANNEL, () => ({ running: runningCommand() }));

// --- Menubar (tray) app -----------------------------------------------------
// This is a menubar utility, NOT a windowed app: a Tray icon shows live status
// and clicking it toggles a small frameless panel (the renderer) anchored under
// the icon. No dock icon. The status/IPC/renderer logic is unchanged — only the
// shell differs.

let tray: Tray | null = null;
let panel: BrowserWindow | null = null;

const PANEL_WIDTH = 360;
const PANEL_MIN_H = 160;
const PANEL_MAX_H = 640; // beyond this the panel scrolls

// Renderer measures its content height and asks us to fit the window to it
// (no scroll until PANEL_MAX_H).
ipcMain.on(PANEL_RESIZE_CHANNEL, (_e, height: number) => {
  if (!panel) return;
  const h = Math.max(PANEL_MIN_H, Math.min(PANEL_MAX_H, Math.ceil(height)));
  panel.setSize(PANEL_WIDTH, h, false);
});

function createPanel(): BrowserWindow {
  const win = new BrowserWindow({
    width: PANEL_WIDTH,
    height: 280,
    show: false,
    frame: false,
    resizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    transparent: true,
    vibrancy: 'popover', // macOS frosted-glass popover look
    visualEffectState: 'active',
    roundedCorners: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    win.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  }
  // Behave like a menubar popover: dismiss when it loses focus.
  win.on('blur', () => win.hide());
  // Tell the renderer when it's visible so it polls ONLY while shown.
  win.on('show', () => win.webContents.send(PANEL_VISIBILITY_CHANNEL, true));
  win.on('hide', () => win.webContents.send(PANEL_VISIBILITY_CHANNEL, false));
  return win;
}

function togglePanel(): void {
  if (!panel || !tray) return;
  if (panel.isVisible()) {
    panel.hide();
    return;
  }
  const tb = tray.getBounds();
  const pb = panel.getBounds();
  const x = Math.round(tb.x + tb.width / 2 - pb.width / 2);
  const y = Math.round(tb.y + tb.height);
  panel.setPosition(x, y, false);
  panel.show();
  panel.focus();
}

/** Mechanized-brain template icon (1x + 2x retina). */
function brainIcon(): Electron.NativeImage {
  const img = nativeImage.createFromDataURL(`data:image/png;base64,${BRAIN_PNG_1X}`);
  img.addRepresentation({ scaleFactor: 2, dataURL: `data:image/png;base64,${BRAIN_PNG_2X}` });
  img.setTemplateImage(true); // macOS tints for light/dark
  return img;
}

/** At-a-glance recording indicator next to the brain icon — ONLY shown while
 *  recording is on. Stopped ⇒ no glyph (just the brain). */
function trayGlyph(): string {
  const s = getListenerStatus(LISTENERS[0]);
  if (!s.running) return '';
  return s.zombieSuspected ? ' ◍' : ' ●';
}

app.on('ready', () => {
  app.dock?.hide(); // menubar-only — no dock icon
  tray = new Tray(brainIcon());
  tray.setToolTip('llm-wiki');
  tray.setTitle(trayGlyph());
  tray.on('click', togglePanel); // click → panel (autostart/quit live in the panel footer)
  panel = createPanel();

  // First launch → guided onboarding (vault detect + FDA grant + start-at-login).
  if (!hasOnboarded()) openOnboarding();

  // Global hotkey: ⌥-Space toggles the panel from anywhere (focuses the Ask field).
  globalShortcut.register('Alt+Space', togglePanel);

  // Lightweight background check for the menubar glyph (visible even when the
  // panel is closed) — slow cadence; the panel does its own faster poll only
  // while visible.
  setInterval(updateTrayTitle, 15000);
  // Pending-work badge — heavier (spawns `wiki menu`), so a slow cadence.
  setTimeout(() => void refreshBadge(), 8000);
  setInterval(() => void refreshBadge(), 300000); // every 5 min
});

// Menubar app: do NOT quit when the panel hides/closes — it lives in the tray.
app.on('window-all-closed', () => {
  // intentionally empty on all platforms; quit via Cmd+Q / the panel's Quit button.
});

app.on('will-quit', () => globalShortcut.unregisterAll());
