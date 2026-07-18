import { describe, it, expect } from 'vitest';
import { parseCollectors } from './collectors';

const TABLE = [
  'NAME                 CONFIGURED         OUTPUT                       PIGGYBACK',
  '──────────────────────────────────────────────────────────────────────────',
  'email                ✓                  raw/notes/email              auto',
  'browser              ✗                  raw/notes/browser            manual-only',
  'calendar             ✓                  raw/notes/calendar           auto',
].join('\n');

describe('parseCollectors', () => {
  it('reads NAME + ✓/✗ rows and skips header/divider lines', () => {
    expect(parseCollectors(TABLE)).toEqual([
      { name: 'email', configured: true },
      { name: 'browser', configured: false },
      { name: 'calendar', configured: true },
    ]);
  });

  it('returns [] for empty output', () => {
    expect(parseCollectors('')).toEqual([]);
  });
});
