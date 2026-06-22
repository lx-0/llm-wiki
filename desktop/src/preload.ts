// Preload — runs with contextIsolation ON. Exposes a minimal, typed API to the
// renderer; the renderer never touches Node directly.

import { contextBridge, ipcRenderer } from 'electron';
import { LISTENER_STATUS_CHANNEL, type ListenerApi } from './listeners/ipc';

const api: ListenerApi = {
  status: () => ipcRenderer.invoke(LISTENER_STATUS_CHANNEL),
};

contextBridge.exposeInMainWorld('listeners', api);
