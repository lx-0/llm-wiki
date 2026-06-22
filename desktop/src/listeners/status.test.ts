import { describe, it, expect } from 'vitest';
import { channelStatus, deriveStatus, getListenerStatus, FRESH_SEC, ZOMBIE_SYS_STALE_SEC } from './status';
import { LISTENERS } from './registry';

const NOW = 1_750_000_000_000; // fixed clock for deterministic tests
const sAgo = (s: number) => NOW - s * 1000;

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
    const s = deriveStatus({ id: 'x', running: true, micLastMs: sAgo(60), sysLastMs: sAgo(ZOMBIE_SYS_STALE_SEC + 60), nowMs: NOW });
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
