import { app, BrowserWindow, ipcMain, Tray, nativeImage } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';
import { LISTENERS, getListener } from './listeners/registry';
import { getListenerStatus } from './listeners/status';
import { startListener, stopListener, restartListener, type LifecycleAction, type LifecycleResult } from './listeners/lifecycle';
import { LISTENER_STATUS_CHANNEL, LISTENER_CONTROL_CHANNEL } from './listeners/ipc';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

// IPC: listener status (system data — launchd + sqlite, read directly; no engine call).
ipcMain.handle(LISTENER_STATUS_CHANNEL, () => {
  const all = LISTENERS.map((l) => getListenerStatus(l));
  console.log(`${LISTENER_STATUS_CHANNEL} -> ${JSON.stringify(all)}`);
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
  console.log(`${LISTENER_CONTROL_CHANNEL} ${id}/${action} -> ${JSON.stringify(res)}`);
  return res;
});

// --- Menubar (tray) app -----------------------------------------------------
// This is a menubar utility, NOT a windowed app: a Tray icon shows live status
// and clicking it toggles a small frameless panel (the renderer) anchored under
// the icon. No dock icon. The status/IPC/renderer logic is unchanged — only the
// shell differs.

let tray: Tray | null = null;
let panel: BrowserWindow | null = null;

function createPanel(): BrowserWindow {
  const win = new BrowserWindow({
    width: 380,
    height: 200,
    show: false,
    frame: false,
    resizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    win.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  }
  // Behave like a menubar popover: dismiss when it loses focus.
  win.on('blur', () => win.hide());
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

/** Menubar title glyph from live status (visible without opening the panel). */
function trayGlyph(): string {
  const s = getListenerStatus(LISTENERS[0]);
  return !s.running ? '○' : s.zombieSuspected ? '◍' : '●';
}

app.on('ready', () => {
  app.dock?.hide(); // menubar-only — no dock icon
  tray = new Tray(nativeImage.createEmpty());
  tray.setToolTip('llm-wiki');
  tray.setTitle(trayGlyph());
  tray.on('click', togglePanel);
  panel = createPanel();
  // Refresh the menubar glyph on its own cadence (visible even when panel closed).
  setInterval(() => tray?.setTitle(trayGlyph()), 5000);
});

// Menubar app: do NOT quit when the panel hides/closes — it lives in the tray.
app.on('window-all-closed', () => {
  // intentionally empty on all platforms; quit via Cmd+Q / future tray menu.
});
