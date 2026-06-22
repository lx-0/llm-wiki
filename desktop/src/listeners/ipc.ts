// Shared IPC contract — imported by BOTH main and preload so the channel name and
// the API shape never drift between the two sides (DRY).

import type { ListenerStatus } from './status';

export const LISTENER_STATUS_CHANNEL = 'listeners:status';

/** The surface exposed to the renderer via contextBridge as `window.listeners`. */
export interface ListenerApi {
  status(): Promise<ListenerStatus[]>;
}
