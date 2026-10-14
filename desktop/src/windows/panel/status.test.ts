import { describe, expect, it } from 'vitest';
import { captureSummary, healthSummary } from './status';

// Wed 2026-10-14 15:00 local
const NOW = new Date(2026, 9, 14, 15, 0, 0).getTime();

describe('healthSummary', () => {
  it('reports the worst severity with a count and a word', () => {
    const checks = (sev: string[]) => ({
      issues: sev.length,
      updateAvailable: false,
      checks: sev.map((severity, i) => ({ id: `c${i}`, severity, message: 'm', title: 'T', verb: null })),
    });
    expect(healthSummary(checks([]))).toEqual({ level: 'ok', count: 0, word: 'OK' });
    expect(healthSummary(checks(['warning']))).toEqual({ level: 'warn', count: 1, word: 'issue' });
    expect(healthSummary(checks(['warning', 'critical', 'warning']))).toEqual({
      level: 'critical',
      count: 3,
      word: 'issues',
    });
  });

  it('is unknown without a doctor result', () => {
    expect(healthSummary(null)).toEqual({ level: 'unknown', count: 0, word: '—' });
  });
});

describe('captureSummary', () => {
  const listener = (running: boolean, micAge: number | null, sysAge: number | null, zombie = false) => ({
    id: 'screenpipe',
    running,
    zombieSuspected: zombie,
    channels: {
      mic: {
        lastCaptureAtMs: micAge == null ? null : NOW - micAge * 1000,
        ageSeconds: micAge,
        fresh: micAge != null && micAge <= 120,
      },
      system: {
        lastCaptureAtMs: sysAge == null ? null : NOW - sysAge * 1000,
        ageSeconds: sysAge,
        fresh: sysAge != null && sysAge <= 120,
      },
    },
    checkedAtMs: NOW,
  });

  it('maps freshness to a 0..1 level that decays to the stale threshold', () => {
    const s = captureSummary(listener(true, 20, 600), new Map());
    expect(s.state).toBe('recording');
    expect(s.word).toBe('Recording');
    expect(s.mic).toBe(1);
    expect(s.system).toBeCloseTo(0.5, 2); // 600 of 1200 s
  });

  it('reads paused, check and in-flight toggles as words', () => {
    expect(captureSummary(listener(false, 3000, null), new Map()).word).toBe('Paused');
    expect(captureSummary(listener(true, 20, 2000, true), new Map()).word).toBe('Check');
    expect(captureSummary(listener(false, null, null), new Map([['screenpipe', 'start']])).word).toBe(
      'Starting…',
    );
    expect(captureSummary(listener(true, 20, 20), new Map([['screenpipe', 'stop']])).word).toBe('Stopping…');
  });

  it('says so when no capture process exists', () => {
    expect(captureSummary(null, new Map())).toEqual({
      state: 'none',
      word: 'Not configured',
      mic: 0,
      system: 0,
    });
  });
});
