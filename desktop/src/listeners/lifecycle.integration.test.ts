// LIVE integration test — toggles the REAL screenpipe listener (stop → start) and
// asserts capture halts then resumes. Guarded: skipped unless LIVE_LISTENER_TEST=1,
// so normal `vitest run` (and CI) never mutates the operator's daemon.
//
//   LIVE_LISTENER_TEST=1 npx vitest run src/listeners/lifecycle.integration.test.ts

import { describe, it, expect } from 'vitest';
import { LISTENERS } from './registry';
import { isRunning, lastChunkMs } from './status';
import { startListener, stopListener } from './lifecycle';

const LIVE = process.env.LIVE_LISTENER_TEST === '1';
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe.skipIf(!LIVE)('lifecycle live (toggles real screenpipe)', () => {
  it(
    'stop halts the daemon, start resumes it and capture',
    async () => {
      const def = LISTENERS[0];

      // Ensure we begin running (start is a no-op if already up).
      startListener(def);
      await sleep(2000);
      expect(isRunning(def.launchdLabel)).toBe(true);

      // STOP → daemon should be gone.
      const stopRes = stopListener(def);
      expect(stopRes.ok).toBe(true);
      await sleep(3000);
      expect(isRunning(def.launchdLabel)).toBe(false);
      const beforeMs = lastChunkMs(def.dbPath, def.channels.mic) ?? 0;

      // START → daemon back + a NEW mic chunk lands (capture resumed).
      const startRes = startListener(def);
      expect(startRes.ok).toBe(true);
      await sleep(2000);
      expect(isRunning(def.launchdLabel)).toBe(true);

      await sleep(50_000); // chunks land ~every 30 s
      const afterMs = lastChunkMs(def.dbPath, def.channels.mic) ?? 0;
      expect(afterMs).toBeGreaterThan(beforeMs);
    },
    80_000,
  );
});
