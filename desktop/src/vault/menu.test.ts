import { describe, it, expect } from 'vitest';
import { parseMenu } from './menu';

describe('parseMenu', () => {
  it('sorts suggestions by priority and defaults missing fields', () => {
    const json = JSON.stringify({
      status: { articles: 12, ollama_reachable: true },
      suggestions: [
        { count: 3, label: 'Review scans', cmd: 'review-wiki', priority: 5, group: 'quality' },
        { label: 'Refresh entities', cmd: 'dream --all-entities', priority: 1, group: 'synthesis' },
      ],
    });
    const m = parseMenu(json);
    expect(m.status).toEqual({ articles: 12, ollama_reachable: true });
    expect(m.suggestions.map((s) => s.cmd)).toEqual(['dream --all-entities', 'review-wiki']);
    expect(m.suggestions[0]).toEqual({
      count: 0,
      label: 'Refresh entities',
      cmd: 'dream --all-entities',
      priority: 1,
      group: 'synthesis',
    });
  });

  it('missing suggestions → empty list, empty status', () => {
    const m = parseMenu('{}');
    expect(m.suggestions).toEqual([]);
    expect(m.status).toEqual({});
  });

  it('throws on malformed JSON (runWiki turns this into data=null)', () => {
    expect(() => parseMenu('<html>')).toThrow();
  });
});
