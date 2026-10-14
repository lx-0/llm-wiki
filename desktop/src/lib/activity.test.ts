import { describe, expect, it } from 'vitest';
import { activity, countPerDay, daysAgo } from './activity';

// Wed 2026-10-14 15:00 local
const NOW = new Date(2026, 9, 14, 15, 0, 0).getTime();
const at = (days: number, hour = 12) => new Date(2026, 9, 14 - days, hour).getTime();
const entry = (mtimeMs: number) => ({ mtimeMs });

describe('daysAgo', () => {
  it('counts whole local calendar days, not 24 h spans', () => {
    expect(daysAgo(at(0, 1), NOW)).toBe(0);
    expect(daysAgo(at(1, 23), NOW)).toBe(1);
    expect(daysAgo(new Date(2026, 9, 15, 2).getTime(), NOW)).toBe(-1);
  });
});

describe('countPerDay', () => {
  it('buckets by local calendar day, oldest first, today last', () => {
    const entries = [
      entry(at(0, 9)),
      entry(at(0, 1)),
      entry(at(1)),
      entry(at(13)),
      entry(at(14)),
      entry(at(40)),
    ];
    const days = countPerDay(entries, NOW, 14);
    expect(days).toHaveLength(14);
    expect(days[13]).toBe(2); // today
    expect(days[12]).toBe(1); // yesterday
    expect(days[0]).toBe(1); // 13 days ago is the oldest bucket
    expect(days.reduce((a, b) => a + b, 0)).toBe(4); // 14 and 40 days ago fall out
  });

  it('crosses a month boundary without gaps', () => {
    const now = new Date(2026, 10, 2, 10).getTime(); // 2 Nov
    const days = countPerDay([entry(new Date(2026, 9, 31, 8).getTime())], now, 5);
    expect(days).toEqual([0, 0, 1, 0, 0]);
  });
});

describe('activity', () => {
  it('counts today and the last seven days', () => {
    const entries = [entry(at(0)), entry(at(0)), entry(at(3)), entry(at(6, 23)), entry(at(8))];
    expect(activity(entries, NOW)).toEqual({ today: 2, week: 4 });
  });
});
