// Listener registry — the single declarative list of long-running capture
// daemons the app supervises. One entry today (screenpipe); this prefigures the
// engine-side `listener-lifecycle` registry (see .ytstack/backlog/listener-lifecycle.md).
//
// NOTE (MVP): the launchd label + db path are operator-specific (`alex`). When the
// listener-lifecycle subsystem lands, these become per-install config, not constants.

import os from 'node:os';
import path from 'node:path';

export interface ListenerDef {
  /** stable id used by the UI + IPC */
  id: string;
  /** human label for the UI */
  name: string;
  /** launchd label, for `launchctl list <label>` running-state */
  launchdLabel: string;
  /** sqlite db the listener writes (read-only by the app) */
  dbPath: string;
  /** `audio_chunks.file_path LIKE` patterns per channel, for freshness */
  channels: { mic: string; system: string };
}

export const LISTENERS: ListenerDef[] = [
  {
    id: 'screenpipe',
    name: 'Screenpipe',
    launchdLabel: 'com.alex.screenpipe',
    dbPath: path.join(os.homedir(), '.screenpipe', 'db.sqlite'),
    channels: { mic: '%Microphone%', system: '%System Audio%' },
  },
];

export function getListener(id: string): ListenerDef | undefined {
  return LISTENERS.find((l) => l.id === id);
}
