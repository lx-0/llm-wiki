import { describe, expect, it, vi } from 'vitest';
import { parseDoctor } from './doctor';

const payload = (checks: unknown[], schema: unknown = 2) => JSON.stringify({ schema, checks });

describe('parseDoctor', () => {
  it('splits actionable issues from the update-available check and keeps title/verb/dispatch_args', () => {
    const d = parseDoctor(
      payload([
        {
          id: 'engine-update-available',
          severity: 'warning',
          message: '36 commits behind origin/main',
          title: 'Engine update available (36 commits behind)',
          verb: 'Update',
          dispatch_args: ['update'],
        },
        {
          id: 'gmail-auth',
          severity: 'critical',
          message: 'Gmail OAuth not bootstrapped for account `work`',
          title: 'Sign in to Gmail (work)',
          verb: 'Sign in',
          fix: 'wiki gmail-auth work',
          dispatch_args: ['gmail-auth', 'work'],
        },
        {
          id: 'claude-authed',
          severity: 'warning',
          message: 'no ANTHROPIC_API_KEY env',
          title: 'no ANTHROPIC_API_KEY env',
          verb: null,
        },
        { id: 'all-good', severity: 'ok', message: 'fine', title: 'fine', verb: null },
      ]),
    );
    expect(d.updateAvailable).toBe(true);
    expect(d.updateMessage).toBe('36 commits behind origin/main');
    expect(d.issues).toBe(2);
    expect(d.checks.map((c) => c.id)).toEqual(['gmail-auth', 'claude-authed']);
    expect(d.checks[0]).toEqual({
      id: 'gmail-auth',
      severity: 'critical',
      message: 'Gmail OAuth not bootstrapped for account `work`',
      title: 'Sign in to Gmail (work)',
      verb: 'Sign in',
      fix: 'wiki gmail-auth work',
      dispatchArgs: ['gmail-auth', 'work'],
    });
    expect(d.checks[1].verb).toBeNull();
    expect(d.checks[1].dispatchArgs).toBeUndefined();
  });

  it('falls back to the message when a check carries no title', () => {
    const d = parseDoctor(payload([{ id: 'x', severity: 'warning', message: 'plain message' }]));
    expect(d.checks[0].title).toBe('plain message');
  });

  it('refuses an unknown schema with no issues and a warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const d = parseDoctor(payload([{ id: 'gmail-auth', severity: 'critical', message: 'x' }], null));
    expect(d.issues).toBe(0);
    expect(d.checks).toEqual([]);
    expect(d.updateAvailable).toBe(false);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('schema'));
    warn.mockRestore();
  });

  it('no checks → no issues, no update', () => {
    const d = parseDoctor(payload([]));
    expect(d.issues).toBe(0);
    expect(d.updateAvailable).toBe(false);
  });

  it('throws on malformed JSON (runWiki turns this into data=null)', () => {
    expect(() => parseDoctor('not json')).toThrow();
  });
});
