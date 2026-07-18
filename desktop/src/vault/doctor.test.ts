import { describe, it, expect } from 'vitest';
import { parseDoctor } from './doctor';

describe('parseDoctor', () => {
  it('splits actionable issues from the update-available check and maps dispatch_args', () => {
    const json = JSON.stringify({
      checks: [
        { id: 'engine-update-available', severity: 'warning', message: '36 commits behind origin/main' },
        { id: 'gmail-auth', severity: 'critical', message: 'token expired', fix: 'wiki gmail-auth work' },
        { id: 'stale-lint', severity: 'warning', message: 'edits since last lint', dispatch_args: ['lint', '--structural-only'] },
        { id: 'all-good', severity: 'ok', message: 'fine' },
      ],
    });
    const d = parseDoctor(json);
    expect(d.updateAvailable).toBe(true);
    expect(d.updateMessage).toBe('36 commits behind origin/main');
    expect(d.issues).toBe(2);
    expect(d.checks.map((c) => c.id)).toEqual(['gmail-auth', 'stale-lint']);
    expect(d.checks[0].fix).toBe('wiki gmail-auth work');
    expect(d.checks[1].dispatchArgs).toEqual(['lint', '--structural-only']);
  });

  it('detects an update from a "behind" message even without warning severity', () => {
    const d = parseDoctor(
      JSON.stringify({ checks: [{ id: 'engine-update-available', severity: 'info', message: '2 behind' }] }),
    );
    expect(d.updateAvailable).toBe(true);
  });

  it('no checks → no issues, no update', () => {
    const d = parseDoctor('{}');
    expect(d.issues).toBe(0);
    expect(d.updateAvailable).toBe(false);
  });

  it('throws on malformed JSON (runWiki turns this into data=null)', () => {
    expect(() => parseDoctor('not json')).toThrow();
  });
});
