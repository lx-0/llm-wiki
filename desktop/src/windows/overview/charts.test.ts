import { describe, expect, it } from 'vitest';
import { columnScale, dayAxis, statTiles } from './charts';

// Wednesday 2026-10-14, noon local — the axis is built on the operator's calendar.
const NOW = new Date(2026, 9, 14, 12).getTime();
const DAY = 86_400_000;

describe('dayAxis', () => {
  it('keys one local day per bin, oldest first, today last', () => {
    const axis = dayAxis(NOW, 30);
    expect(axis.days).toHaveLength(30);
    expect(axis.days[29].key).toBe('2026-10-14');
    expect(axis.days[0].key).toBe('2026-09-15');
    expect(axis.days[29].name).toBe('Wed 14 Oct');
  });

  it('labels every Monday and today — a Monday within three days of today yields to Today', () => {
    const axis = dayAxis(NOW, 30);
    expect(axis.ticks).toEqual([
      { index: 6, label: '21 Sep' },
      { index: 13, label: '28 Sep' },
      { index: 20, label: '5 Oct' },
      { index: 29, label: 'Today' },
    ]);
    // Thursday: Monday is three days back and keeps its tick
    const thursday = new Date(2026, 9, 15, 12).getTime();
    expect(dayAxis(thursday, 7).ticks).toEqual([
      { index: 3, label: '12 Oct' },
      { index: 6, label: 'Today' },
    ]);
  });

  it('a Monday today is labelled Today, not twice', () => {
    const monday = new Date(2026, 9, 12, 9).getTime();
    const axis = dayAxis(monday, 8);
    expect(axis.ticks).toEqual([
      { index: 0, label: '5 Oct' },
      { index: 7, label: 'Today' },
    ]);
  });
});

describe('columnScale', () => {
  it('rounds the maximum up to a clean number and ticks 0 and max', () => {
    expect(columnScale([4, 7, 2])).toEqual({ max: 10, ticks: [0, 10] });
    expect(columnScale([12])).toEqual({ max: 20, ticks: [0, 20] });
    expect(columnScale([3])).toEqual({ max: 5, ticks: [0, 5] });
    expect(columnScale([150, 40])).toEqual({ max: 200, ticks: [0, 200] });
  });

  it('keeps a visible scale when there is nothing to show', () => {
    expect(columnScale([0, 0])).toEqual({ max: 1, ticks: [0, 1] });
    expect(columnScale([])).toEqual({ max: 1, ticks: [0, 1] });
  });
});

describe('statTiles', () => {
  it('reads today / week from mtimes and passes inbox + issues through', () => {
    const entries = [{ mtimeMs: NOW - 60_000 }, { mtimeMs: NOW - 2 * DAY }, { mtimeMs: NOW - 20 * DAY }];
    expect(statTiles({ entries, inbox: 5, issues: 3, now: NOW })).toEqual([
      { label: 'Updated today', value: '1' },
      { label: 'This week', value: '2' },
      { label: 'Inbox', value: '5' },
      { label: 'Issues', value: '3' },
    ]);
  });
});
