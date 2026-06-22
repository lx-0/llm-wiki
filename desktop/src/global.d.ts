import type { ListenerApi } from './listeners/ipc';
import type { VaultApi } from './vault/ipc';
import type { PanelApi } from './panel/ipc';

declare global {
  interface Window {
    /** Exposed by preload.ts via contextBridge. See src/listeners/ipc.ts. */
    listeners: ListenerApi;
    /** Exposed by preload.ts via contextBridge. See src/vault/ipc.ts. */
    vault: VaultApi;
    /** Exposed by preload.ts via contextBridge. See src/panel/ipc.ts. */
    panel: PanelApi;
  }
}

export {};
