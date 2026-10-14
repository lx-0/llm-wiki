import { describe, expect, it } from 'vitest';
import { capRows, type Entry, filterEntries, typeChips, typeCounts } from './filter';

const e = (title: string, type: string, file = `knowledge/${type}s/${title}.md`): Entry => ({
  title,
  type,
  file,
  mtimeMs: 0,
});
const ALL: Entry[] = [
  e('Sid Rahman', 'person'),
  e('Fleet', 'project'),
  e('Dream cycle', 'concept'),
  e('Fleet MOC', 'map'),
];

describe('filterEntries', () => {
  it('matches title or file, case-insensitively, and narrows by type', () => {
    expect(filterEntries(ALL, 'fleet', '').map((x) => x.title)).toEqual(['Fleet', 'Fleet MOC']);
    expect(filterEntries(ALL, 'FLEET', 'map').map((x) => x.title)).toEqual(['Fleet MOC']);
    expect(filterEntries(ALL, 'projects/', '').map((x) => x.title)).toEqual(['Fleet']);
  });

  it('returns everything for an empty query and no type', () => {
    expect(filterEntries(ALL, '   ', '')).toHaveLength(4);
  });
});

describe('capRows', () => {
  it('caps the list and reports how many are hidden', () => {
    const many = Array.from({ length: 5 }, (_, i) => e(`n${i}`, 'note'));
    expect(capRows(many, 3)).toEqual({ shown: many.slice(0, 3), hidden: 2 });
    expect(capRows(many, 10)).toEqual({ shown: many, hidden: 0 });
  });
});

describe('typeCounts + typeChips', () => {
  it('orders the known kinds canonically and unknown kinds after, with counts', () => {
    const rows = [...ALL, e('x', 'recipe'), e('y', 'person')];
    expect(typeCounts(rows)).toEqual([
      { type: 'person', count: 2 },
      { type: 'project', count: 1 },
      { type: 'concept', count: 1 },
      { type: 'map', count: 1 },
      { type: 'recipe', count: 1 },
    ]);
    expect(typeChips(rows)).toEqual(['person', 'project', 'concept', 'map', 'recipe']);
  });
});
