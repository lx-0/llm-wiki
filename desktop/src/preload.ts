// Preload — runs with contextIsolation ON. Exposes minimal, typed APIs to the
// renderer (one global per domain); the renderer never touches Node directly.

import { contextBridge, ipcRenderer } from 'electron';
import { LISTENER_STATUS_CHANNEL, LISTENER_CONTROL_CHANNEL, type ListenerApi } from './listeners/ipc';
import {
  VAULT_STATUS_CHANNEL,
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
  type VaultApi,
} from './vault/ipc';
import { PANEL_VISIBILITY_CHANNEL, PANEL_RESIZE_CHANNEL, type PanelApi } from './panel/ipc';
import {
  APP_LOGIN_GET_CHANNEL,
  APP_LOGIN_SET_CHANNEL,
  APP_QUIT_CHANNEL,
  APP_OPEN_SETTINGS_CHANNEL,
  type AppApi,
} from './app/ipc';

const listeners: ListenerApi = {
  status: () => ipcRenderer.invoke(LISTENER_STATUS_CHANNEL),
  control: (id, action) => ipcRenderer.invoke(LISTENER_CONTROL_CHANNEL, id, action),
};

const vault: VaultApi = {
  status: () => ipcRenderer.invoke(VAULT_STATUS_CHANNEL),
  openInObsidian: () => ipcRenderer.invoke(VAULT_OPEN_OBSIDIAN_CHANNEL),
  openFile: (file) => ipcRenderer.send(VAULT_OPEN_FILE_CHANNEL, file),
  openFullDiskAccess: () => ipcRenderer.send(VAULT_OPEN_FDA_CHANNEL),
  compile: () => ipcRenderer.invoke(VAULT_COMPILE_CHANNEL),
  compileStatus: () => ipcRenderer.invoke(VAULT_COMPILE_STATUS_CHANNEL),
  onCompileProgress: (cb) => ipcRenderer.on(VAULT_COMPILE_PROGRESS_CHANNEL, (_e, p) => cb(p)),
  onCompileDone: (cb) => ipcRenderer.on(VAULT_COMPILE_DONE_CHANNEL, (_e, r) => cb(r)),
  doctor: () => ipcRenderer.invoke(VAULT_DOCTOR_CHANNEL),
  query: (question) => ipcRenderer.invoke(VAULT_QUERY_CHANNEL, question),
  menu: () => ipcRenderer.invoke(VAULT_MENU_CHANNEL),
  run: (id) => ipcRenderer.invoke(VAULT_RUN_CHANNEL, id),
  runArgs: (args) => ipcRenderer.invoke(VAULT_RUN_ARGS_CHANNEL, args),
  runStatus: () => ipcRenderer.invoke(VAULT_RUN_STATUS_CHANNEL),
  onRunProgress: (cb) => ipcRenderer.on(VAULT_RUN_PROGRESS_CHANNEL, (_e, r) => cb(r)),
  onRunDone: (cb) => ipcRenderer.on(VAULT_RUN_DONE_CHANNEL, (_e, r) => cb(r)),
};

const panel: PanelApi = {
  onVisibility: (cb) => ipcRenderer.on(PANEL_VISIBILITY_CHANNEL, (_e, v: boolean) => cb(v)),
  resize: (height) => ipcRenderer.send(PANEL_RESIZE_CHANNEL, height),
};

const appApi: AppApi = {
  getLoginItem: () => ipcRenderer.invoke(APP_LOGIN_GET_CHANNEL),
  setLoginItem: (open) => ipcRenderer.invoke(APP_LOGIN_SET_CHANNEL, open),
  quit: () => ipcRenderer.send(APP_QUIT_CHANNEL),
  openSettings: () => ipcRenderer.send(APP_OPEN_SETTINGS_CHANNEL),
};

contextBridge.exposeInMainWorld('listeners', listeners);
contextBridge.exposeInMainWorld('vault', vault);
contextBridge.exposeInMainWorld('panel', panel);
contextBridge.exposeInMainWorld('app', appApi);
