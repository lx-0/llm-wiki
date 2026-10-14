// Shared IPC contract — imported by BOTH main and preload so the channel name and
// the API shape never drift between the two sides (DRY).

import type { LifecycleAction, LifecycleResult } from './lifecycle';
import type { CaptureTimeline, ListenerStatus } from './status';

export const LISTENER_STATUS_CHANNEL = 'listeners:status';
export const LISTENER_CONTROL_CHANNEL = 'listeners:control';
export const LISTENER_TIMELINE_CHANNEL = 'listeners:timeline';

/** The surface exposed to the renderer via contextBridge as `window.listeners`. */
export interface ListenerApi {
  status(): Promise<ListenerStatus[]>;
  control(id: string, action: LifecycleAction): Promise<LifecycleResult>;
  /** Hourly mic / system chunk counts over the last `hours` (default 24), newest bin last;
   *  null for an unknown listener. Same sqlite as status, read-only. */
  timeline(id: string, hours?: number): Promise<CaptureTimeline | null>;
}
