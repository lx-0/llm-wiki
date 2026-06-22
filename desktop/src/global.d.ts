import type { ListenerApi } from './listeners/ipc';

declare global {
  interface Window {
    /** Exposed by preload.ts via contextBridge. See src/listeners/ipc.ts. */
    listeners: ListenerApi;
  }
}

export {};
