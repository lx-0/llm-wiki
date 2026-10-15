import { describe, expect, it, vi } from 'vitest';
import { validateDoctor } from '../lib/contract';
import { parseDoctor } from './doctor';

/** One check exactly as the engine sends it: every key present, `null` where it sends null. */
const check = (over: Record<string, unknown>) => ({
  id: 'x',
  category: 'config',
  severity: 'ok',
  message: '',
  fix: null,
  dispatch_args: null,
  details: null,
  title: '',
  verb: null,
  ...over,
});

/** The representative `wiki doctor --json` payload — a full schema-2 envelope. */
const representative = {
  schema: 2,
  vault: 'lxw',
  engine_revision: 'abc1234',
  summary: { critical: 1, warning: 2, info: 0, ok: 1 },
  checks: [
    check({
      id: 'engine-update-available',
      severity: 'warning',
      message: '36 commits behind origin/main',
      title: 'Engine update available (36 commits behind)',
      verb: 'Update',
      dispatch_args: ['update'],
    }),
    check({
      id: 'gmail-auth',
      category: 'connectivity',
      severity: 'critical',
      message: 'Gmail OAuth not bootstrapped for account `work`',
      title: 'Sign in to Gmail (work)',
      verb: 'Sign in',
      fix: 'wiki gmail-auth work',
      dispatch_args: ['gmail-auth', 'work'],
    }),
    check({
      id: 'claude-authed',
      severity: 'warning',
      message: 'no ANTHROPIC_API_KEY env',
      title: 'no ANTHROPIC_API_KEY env',
    }),
    check({ id: 'all-good', message: 'fine', title: 'fine' }),
  ],
};

// Partial on purpose: the parser's fallbacks for input the engine does not send.
const payload = (checks: unknown[], schema: unknown = 2) => JSON.stringify({ schema, checks });

describe('parseDoctor', () => {
  it('reads a payload that conforms to the schema-2 contract', () => {
    expect(validateDoctor(representative)).toEqual([]);
  });

  it('splits actionable issues from the update-available check and keeps title/verb/dispatch_args', () => {
    const d = parseDoctor(JSON.stringify(representative));
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
