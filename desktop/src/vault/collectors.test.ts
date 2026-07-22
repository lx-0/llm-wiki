import { describe, it, expect } from 'vitest';
import { parseCollectors } from './collectors';

const PAYLOAD = JSON.stringify({
  collectors: [
    { name: 'email', configured: true, output: 'raw/notes/email', piggyback: 'auto' },
    { name: 'browser', configured: false, output: 'raw/notes/browser', piggyback: 'manual-only' },
    { name: 'calendar', configured: true, output: 'raw/notes/calendar', piggyback: 'auto' },
  ],
});

describe('parseCollectors', () => {
  it('maps the `wiki collect --list --json` payload to name + configured', () => {
    expect(parseCollectors(PAYLOAD)).toEqual([
      { name: 'email', configured: true },
      { name: 'browser', configured: false },
      { name: 'calendar', configured: true },
    ]);
  });

  it('returns [] for a payload without a collectors array', () => {
    expect(parseCollectors('{}')).toEqual([]);
  });

  it('drops entries without a name and coerces non-boolean configured to false', () => {
    const noisy = JSON.stringify({
      collectors: [{ configured: true }, { name: 'voice', configured: 'yes' }],
    });
    expect(parseCollectors(noisy)).toEqual([{ name: 'voice', configured: false }]);
  });

  it('throws on non-JSON output (runWiki turns that into data=null)', () => {
    expect(() => parseCollectors('NAME  CONFIGURED\nemail  ✓')).toThrow();
  });
});
