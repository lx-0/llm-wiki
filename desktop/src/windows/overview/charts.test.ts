import { describe, expect, it } from 'vitest';
import { columnScale, dayAxis, heatLevel, hourName, hourTicks, statTiles, typeBars } from './charts';

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

describe('typeBars', () => {
  const e = (type: string) => ({ title: 't', file: 'f', type, mtimeMs: NOW });

  it('counts per type, largest first, ties in the canonical kind order, with a rounded share', () => {
    const bars = typeBars([e('concept'), e('person'), e('person'), e('project'), e('concept'), e('fact')]);
    expect(bars).toEqual([
      { type: 'person', count: 2, share: 33 },
      { type: 'concept', count: 2, share: 33 },
      { type: 'project', count: 1, share: 17 },
      { type: 'fact', count: 1, share: 17 },
    ]);
  });

  it('is empty without entries', () => {
    expect(typeBars([])).toEqual([]);
  });
});

describe('heatLevel', () => {
  it('maps chunk counts to quartiles of a full 30 s-cadence hour', () => {
    expect(heatLevel(0)).toBe(0);
    expect(heatLevel(1)).toBe(1);
    expect(heatLevel(30)).toBe(1);
    expect(heatLevel(31)).toBe(2);
    expect(heatLevel(60)).toBe(2);
    expect(heatLevel(90)).toBe(3);
    expect(heatLevel(91)).toBe(4);
    expect(heatLevel(120)).toBe(4);
    expect(heatLevel(500)).toBe(4);
  });
});

describe('hourTicks + hourName', () => {
  const HOUR = 3_600_000;
  // 24 bins ending with the hour that contains NOW (12:00) → the first bin is 13:00 yesterday
  const startMs = new Date(2026, 9, 14, 12).getTime() - 23 * HOUR;

  it('labels 00 / 06 / 12 / 18 and now; a clock tick within two bins of now yields', () => {
    expect(hourTicks(startMs, 24)).toEqual([
      { index: 5, label: '18' },
      { index: 11, label: '00' },
      { index: 17, label: '06' },
      { index: 23, label: 'now' },
    ]);
    // now = 13:00 → the 12:00 bin sits one bin before now and loses its tick
    expect(hourTicks(startMs + HOUR, 24).map((t) => t.label)).toEqual(['18', '00', '06', 'now']);
  });

  it('names a bin as its hour range', () => {
    expect(hourName(startMs, 0)).toBe('13:00–14:00');
    expect(hourName(startMs, 23)).toBe('12:00–13:00');
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
