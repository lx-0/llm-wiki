import { describe, expect, it } from 'vitest';
import { LISTENERS } from './registry';
import {
  bucketByHour,
  channelStatus,
  deriveStatus,
  FRESH_SEC,
  getListenerStatus,
  ZOMBIE_SYS_STALE_SEC,
} from './status';

const NOW = 1_750_000_000_000; // fixed clock for deterministic tests
const sAgo = (s: number) => NOW - s * 1000;
const HOUR = 3_600_000;
/** start of the local hour that contains `ms` — the bins are aligned to the operator's clock */
const hourStart = (ms: number): number => {
  const d = new Date(ms);
  d.setMinutes(0, 0, 0);
  return d.getTime();
};

describe('bucketByHour (pure)', () => {
  const h0 = hourStart(NOW);

  it('empty input → one zero bin per hour, the newest bin being the current hour', () => {
    const t = bucketByHour([], NOW, 24);
    expect(t.bucketMs).toBe(HOUR);
    expect(t.startMs).toBe(h0 - 23 * HOUR);
    expect(t.counts).toHaveLength(24);
    expect(t.counts.every((n) => n === 0)).toBe(true);
    expect(bucketByHour([], NOW, 3).counts).toHaveLength(3);
  });

  it('counts samples into aligned bins; the boundary belongs to the later bin', () => {
    const t = bucketByHour([h0 + 5 * 60_000, h0 + 6 * 60_000, h0 - 1, h0 - 23 * HOUR], NOW, 24);
    expect(t.counts[23]).toBe(2);
    expect(t.counts[22]).toBe(1);
    expect(t.counts[0]).toBe(1);
  });

  it('drops samples outside the window — older than the first bin or past the current hour', () => {
    const t = bucketByHour([h0 - 23 * HOUR - 1, h0 + HOUR, NOW], NOW, 24);
    expect(t.counts.reduce((a, b) => a + b, 0)).toBe(1);
    expect(t.counts[23]).toBe(1);
  });
});

describe('channelStatus (pure)', () => {
  it('null last → not fresh, null age', () => {
    expect(channelStatus(null, NOW)).toEqual({ lastCaptureAtMs: null, ageSeconds: null, fresh: false });
  });
  it('recent → fresh', () => {
    const c = channelStatus(sAgo(30), NOW);
    expect(c.ageSeconds).toBe(30);
    expect(c.fresh).toBe(true);
  });
  it('beyond threshold → stale', () => {
    expect(channelStatus(sAgo(FRESH_SEC + 1), NOW).fresh).toBe(false);
  });
  it('clamps negative age (clock skew) to 0', () => {
    expect(channelStatus(NOW + 5000, NOW).ageSeconds).toBe(0);
  });
});

describe('deriveStatus (pure)', () => {
  it('healthy: running, both channels fresh → no zombie', () => {
    const s = deriveStatus({ id: 'x', running: true, micLastMs: sAgo(20), sysLastMs: sAgo(25), nowMs: NOW });
    expect(s.running).toBe(true);
    expect(s.channels.mic.fresh).toBe(true);
    expect(s.channels.system.fresh).toBe(true);
    expect(s.zombieSuspected).toBe(false);
  });

  it('ZOMBIE: running, mic fresh, system stale beyond threshold → suspected', () => {
    const s = deriveStatus({
      id: 'x',
      running: true,
      micLastMs: sAgo(60),
      sysLastMs: sAgo(ZOMBIE_SYS_STALE_SEC + 60),
      nowMs: NOW,
    });
    expect(s.zombieSuspected).toBe(true);
  });

  it('ZOMBIE: running, mic fresh, system absent (null) → suspected', () => {
    const s = deriveStatus({ id: 'x', running: true, micLastMs: sAgo(60), sysLastMs: null, nowMs: NOW });
    expect(s.zombieSuspected).toBe(true);
  });

  it('NOT zombie when stopped, even if the pattern matches', () => {
    const s = deriveStatus({ id: 'x', running: false, micLastMs: sAgo(60), sysLastMs: null, nowMs: NOW });
    expect(s.zombieSuspected).toBe(false);
  });

  it('NOT zombie when system is merely a bit stale (under threshold)', () => {
    const s = deriveStatus({ id: 'x', running: true, micLastMs: sAgo(60), sysLastMs: sAgo(300), nowMs: NOW });
    expect(s.zombieSuspected).toBe(false);
  });
});

// Live smoke test against the real machine (REGEL #1). screenpipe may be stopped
// (it is, by operator request) — assert SHAPE, not specific values, to stay non-flaky.
describe('getListenerStatus (live I/O smoke)', () => {
  it('returns a well-formed status for the registry entry', () => {
    const s = getListenerStatus(LISTENERS[0]);
    expect(typeof s.running).toBe('boolean');
    expect(s.channels.mic).toHaveProperty('fresh');
    expect(s.channels.system).toHaveProperty('fresh');
    expect(typeof s.zombieSuspected).toBe('boolean');
    expect(s.checkedAtMs).toBeGreaterThan(0);
  });
});
