import type { ListenerApi } from './listeners/ipc';
import type { VaultApi } from './vault/ipc';

declare global {
  interface Window {
    /** Exposed by preload.ts via contextBridge. See src/listeners/ipc.ts. */
    listeners: ListenerApi;
    /** Exposed by preload.ts via contextBridge. See src/vault/ipc.ts. */
    vault: VaultApi;
  }
}

export {};
