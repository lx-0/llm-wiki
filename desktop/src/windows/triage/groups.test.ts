import { describe, expect, it } from 'vitest';
import { groupRecords, metaLine, pendingCount, type TriageRecord } from './groups';

const rec = (over: Partial<TriageRecord>): TriageRecord => ({
  stem: '2026-10-13-x',
  type: 'task',
  status: 'pending',
  summary: 'x',
  source: 'daily/2026-10-13/sessions.md',
  detail: '',
  date: '2026-10-13',
  confidence: 'high',
  ...over,
});

describe('groupRecords', () => {
  it('groups tasks → ideas → notes → other and skips empty groups', () => {
    const groups = groupRecords([
      rec({ stem: 'a', type: 'note' }),
      rec({ stem: 'b', type: 'task' }),
      rec({ stem: 'c', type: 'recipe' }),
    ]);
    expect(groups.map((g) => [g.key, g.label, g.items.map((i) => i.stem)])).toEqual([
      ['task', 'Tasks', ['b']],
      ['note', 'Notes', ['a']],
      ['other', 'Other', ['c']],
    ]);
  });

  it('sorts unsure (low confidence) first, then newest stem first, and counts pending', () => {
    const groups = groupRecords([
      rec({ stem: '2026-10-12-old', confidence: 'high' }),
      rec({ stem: '2026-10-13-new', confidence: 'high' }),
      rec({ stem: '2026-10-11-unsure', confidence: 'low' }),
      rec({ stem: '2026-10-10-done', status: 'accepted' }),
    ]);
    expect(groups[0].items.map((i) => i.stem)).toEqual([
      '2026-10-11-unsure',
      '2026-10-13-new',
      '2026-10-12-old',
      '2026-10-10-done',
    ]);
    expect(groups[0].pending).toBe(3);
  });
});

describe('pendingCount', () => {
  it('counts only pending records', () => {
    expect(pendingCount([rec({}), rec({ status: 'dismissed' })])).toBe(1);
  });
});

describe('metaLine', () => {
  it('reads "from <folder> · <day> <Mon>" and appends the status once resolved', () => {
    expect(metaLine(rec({ source: 'raw/notes/email/gmail-2026-10-13.md', date: '2026-10-13' }))).toBe(
      'from email · 13 Oct',
    );
    expect(metaLine(rec({ source: '', date: '2026-02-03', status: 'accepted' }))).toBe('3 Feb · accepted');
  });

  it('names the file instead of a date folder for daily captures', () => {
    expect(metaLine(rec({ source: 'daily/2026-10-13/sessions.md', date: '2026-10-13' }))).toBe(
      'from an AI chat · 13 Oct',
    );
  });
});
