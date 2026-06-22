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
  type VaultApi,
} from './vault/ipc';
import { PANEL_VISIBILITY_CHANNEL, type PanelApi } from './panel/ipc';

const listeners: ListenerApi = {
  status: () => ipcRenderer.invoke(LISTENER_STATUS_CHANNEL),
  control: (id, action) => ipcRenderer.invoke(LISTENER_CONTROL_CHANNEL, id, action),
};

const vault: VaultApi = {
  status: () => ipcRenderer.invoke(VAULT_STATUS_CHANNEL),
  compile: () => ipcRenderer.invoke(VAULT_COMPILE_CHANNEL),
  compileStatus: () => ipcRenderer.invoke(VAULT_COMPILE_STATUS_CHANNEL),
  onCompileProgress: (cb) => ipcRenderer.on(VAULT_COMPILE_PROGRESS_CHANNEL, (_e, p) => cb(p)),
  onCompileDone: (cb) => ipcRenderer.on(VAULT_COMPILE_DONE_CHANNEL, (_e, r) => cb(r)),
};

const panel: PanelApi = {
  onVisibility: (cb) => ipcRenderer.on(PANEL_VISIBILITY_CHANNEL, (_e, v: boolean) => cb(v)),
};

contextBridge.exposeInMainWorld('listeners', listeners);
contextBridge.exposeInMainWorld('vault', vault);
contextBridge.exposeInMainWorld('panel', panel);
