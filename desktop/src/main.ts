import { app, BrowserWindow, ipcMain } from 'electron';
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

const createWindow = () => {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // and load the index.html of the app.
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }

  // Open the DevTools.
  mainWindow.webContents.openDevTools();
};

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.on('ready', createWindow);

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and import them here.
