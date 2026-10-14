import { describe, expect, it, vi } from 'vitest';
import { parseMenu } from './menu';

const payload = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    schema: 2,
    status: { articles: 12, ollama_reachable: true },
    suggestions: [
      {
        key: '1',
        id: 'suggestions',
        count: 3,
        label: '3 approved suggestions to execute',
        title: '3 approved suggestions to run',
        verb: 'Run',
        group: 'do',
        argv: ['suggestions'],
        priority: 5,
      },
      {
        key: '2',
        id: 'dream-sweep',
        count: 12,
        label: '12 entities overdue for dream',
        title: '12 pages need refreshing',
        verb: 'Refresh',
        group: 'auto',
        argv: ['dream', '--all-entities'],
        priority: 1,
      },
    ],
    tools: [
      {
        id: 'lint',
        title: 'Check for problems',
        verb: 'Check',
        group: 'tools',
        argv: ['lint', '--structural-only'],
      },
    ],
    ...over,
  });

describe('parseMenu', () => {
  it('keeps the engine vocabulary verbatim and sorts suggestions by priority', () => {
    const m = parseMenu(payload());
    expect(m.status).toEqual({ articles: 12, ollama_reachable: true });
    expect(m.suggestions.map((s) => s.id)).toEqual(['dream-sweep', 'suggestions']);
    expect(m.suggestions[0]).toEqual({
      id: 'dream-sweep',
      count: 12,
      label: '12 entities overdue for dream',
      title: '12 pages need refreshing',
      verb: 'Refresh',
      group: 'auto',
      argv: ['dream', '--all-entities'],
      priority: 1,
    });
    expect(m.tools).toEqual([
      {
        id: 'lint',
        title: 'Check for problems',
        verb: 'Check',
        group: 'tools',
        argv: ['lint', '--structural-only'],
      },
    ]);
  });

  it('refuses an unknown schema with empty lists and a warning instead of guessing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const m = parseMenu(JSON.stringify({ status: { articles: 1 }, suggestions: [{ cmd: 'compile' }] }));
    expect(m.suggestions).toEqual([]);
    expect(m.tools).toEqual([]);
    expect(m.status).toEqual({ articles: 1 });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('schema'));
    warn.mockRestore();
  });

  it('drops suggestions without an argv — nothing to dispatch', () => {
    const m = parseMenu(
      payload({
        suggestions: [{ id: 'x', title: 'X', verb: 'Run', group: 'do', priority: 1, count: 1, argv: [] }],
      }),
    );
    expect(m.suggestions).toEqual([]);
  });

  it('throws on malformed JSON (runWiki turns this into data=null)', () => {
    expect(() => parseMenu('<html>')).toThrow();
  });
});
