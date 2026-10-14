// LIVE read-only integration test — reads the operator's real listener db through
// getCaptureTimeline (sqlite3 -readonly; no daemon is touched). Skipped unless
// LIVE_LISTENER_DB=1, so a normal `vitest run` never depends on the machine.
//
//   LIVE_LISTENER_DB=1 npx vitest run src/listeners/status.integration.test.ts

import { describe, expect, it } from 'vitest';
import { LISTENERS } from './registry';
import { getCaptureTimeline } from './status';

const LIVE = process.env.LIVE_LISTENER_DB === '1';

describe.skipIf(!LIVE)('capture timeline live (reads the real listener db)', () => {
  it('returns one bin per hour over 30 days, with recorded mic chunks in the window', () => {
    const hours = 24 * 30;
    const t = getCaptureTimeline(LISTENERS[0], hours);
    expect(t.mic).toHaveLength(hours);
    expect(t.system).toHaveLength(hours);
    const total = t.mic.reduce((a, b) => a + b, 0);
    const busiest = Math.max(...t.mic);
    console.log(
      `live timeline: ${total} mic chunks in 30 days, busiest hour ${busiest}, newest bin ${t.mic[hours - 1]}`,
    );
    expect(total).toBeGreaterThan(0);
  });
});
