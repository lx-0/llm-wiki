import { describe, expect, it } from 'vitest';
import type { Action } from '../../lib/actions';
import { classifyLink, configuredSources, isNew, nextUp, toolRows } from './sections';

const action = (over: Partial<Action>): Action => ({
  key: 'x',
  id: 'x',
  title: 'X',
  verb: 'Run',
  group: 'do',
  argv: ['x'],
  severity: null,
  count: null,
  sources: ['menu'],
  ...over,
});

const ROWS: Action[] = [
  action({ key: 'hooks install', id: 'hooks', severity: 'warning', group: 'do', sources: ['doctor'] }),
  action({ key: 'process-inbox', id: 'process-inbox', group: 'do', count: 3 }),
  action({ key: 'curiosity --type folder-deep-scan', id: 'curiosity-folder', group: 'review' }),
  action({
    key: 'dream --all-entities',
    id: 'dream-sweep',
    group: 'auto',
    count: 12,
    sources: ['menu', 'tool'],
  }),
  action({ key: 'lint --structural-only', id: 'lint', group: 'auto', sources: ['menu', 'tool'] }),
  action({ key: 'links', id: 'links', group: 'tools', sources: ['tool'] }),
  action({ key: 'dedup --suggest-only', id: 'dedup', group: 'tools', sources: ['tool'] }),
];

describe('nextUp', () => {
  it('keeps pending rows in order, drops pure tools, and caps the list', () => {
    expect(nextUp(ROWS).map((r) => r.id)).toEqual([
      'hooks',
      'process-inbox',
      'curiosity-folder',
      'dream-sweep',
      'lint',
    ]);
    expect(nextUp(ROWS, 3).map((r) => r.id)).toEqual(['hooks', 'process-inbox', 'curiosity-folder']);
  });

  it('is empty for a quiet vault even when tools exist', () => {
    expect(nextUp(ROWS.filter((r) => r.group === 'tools'))).toEqual([]);
  });
});

describe('toolRows', () => {
  it('lists every tool-backed action once, pure tools and probe-backed ones alike', () => {
    expect(toolRows(ROWS).map((r) => r.id)).toEqual(['dream-sweep', 'lint', 'links', 'dedup']);
  });
});

describe('classifyLink', () => {
  it('routes YouTube and web links to the right ingest command', () => {
    expect(classifyLink('https://youtu.be/abc')).toEqual(['ingest-youtube', '--url', 'https://youtu.be/abc']);
    expect(classifyLink('https://www.youtube.com/watch?v=abc')).toEqual([
      'ingest-youtube',
      '--url',
      'https://www.youtube.com/watch?v=abc',
    ]);
    expect(classifyLink('http://example.com/post')).toEqual(['ingest-html', 'http://example.com/post']);
  });

  it('rejects anything that is not a link', () => {
    expect(classifyLink('hello')).toBeNull();
    expect(classifyLink('')).toBeNull();
  });
});

describe('isNew', () => {
  it('marks entries modified after the last look', () => {
    expect(isNew({ mtimeMs: 200 }, 100)).toBe(true);
    expect(isNew({ mtimeMs: 100 }, 100)).toBe(false);
  });
});

describe('configuredSources', () => {
  it('keeps configured collectors only, in engine order', () => {
    expect(
      configuredSources([
        { name: 'email', configured: true },
        { name: 'browser', configured: false },
        { name: 'voice', configured: true },
      ]).map((c) => c.name),
    ).toEqual(['email', 'voice']);
  });
});
