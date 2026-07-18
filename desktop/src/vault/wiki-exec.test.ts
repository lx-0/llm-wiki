import { describe, it, expect, vi } from 'vitest';
import { EventEmitter } from 'node:events';
import os from 'node:os';
import {
  augmentedPath,
  wikiBin,
  ANSI,
  parseJson,
  collectChild,
  type ChildLike,
  type WikiResult,
} from './wiki-exec';

// A fake ChildProcess: EventEmitter-backed stdout/stderr + a kill spy. Lets us drive
// collectChild's collection / strip / parse / timeout / kill logic without a real spawn.
function makeFakeChild() {
  const stdout = new EventEmitter();
  const stderr = new EventEmitter();
  const bus = new EventEmitter();
  const kills: (NodeJS.Signals | number | undefined)[] = [];
  const child = {
    stdout,
    stderr,
    on(event: 'exit' | 'error', listener: (...args: never[]) => void) {
      bus.on(event, listener as (...args: unknown[]) => void);
      return child;
    },
    kill(signal?: NodeJS.Signals | number) {
      kills.push(signal);
      return true;
    },
  } as unknown as ChildLike;
  return {
    child,
    kills,
    pushOut: (s: string) => stdout.emit('data', Buffer.from(s)),
    pushErr: (s: string) => stderr.emit('data', Buffer.from(s)),
    exit: (code: number | null) => bus.emit('exit', code),
    fail: (e: Error) => bus.emit('error', e),
  };
}

describe('path helpers (pure)', () => {
  it('augmentedPath prepends Homebrew + user bin ahead of the inherited PATH', () => {
    const p = augmentedPath();
    expect(p.startsWith('/opt/homebrew/bin:')).toBe(true);
    expect(p).toContain(os.homedir());
  });
  it('wikiBin points at the vault wrapper', () => {
    expect(wikiBin('/vault')).toBe('/vault/.wiki/wiki');
  });
  it('ANSI strips SGR escape codes', () => {
    expect('\x1b[31mred\x1b[0m'.replace(ANSI, '')).toBe('red');
  });
});

describe('parseJson', () => {
  it('parses well-formed JSON', () => {
    expect(parseJson<{ a: number }>('{"a":1}')).toEqual({ a: 1 });
  });
  it('throws on malformed JSON (so runWiki falls back to data=null)', () => {
    expect(() => parseJson('')).toThrow();
  });
});

describe('collectChild', () => {
  it('collects stdout+stderr, strips ANSI, ok on exit 0', async () => {
    const f = makeFakeChild();
    const p = collectChild(f.child);
    f.pushOut('\x1b[32mhello\x1b[0m');
    f.pushErr('warn');
    f.exit(0);
    const r = await p;
    expect(r.ok).toBe(true);
    expect(r.code).toBe(0);
    expect(r.stdout).toBe('hello');
    expect(r.stderr).toBe('warn');
    expect(r.error).toBeNull();
  });

  it('non-zero exit → ok false, code preserved, no error object', async () => {
    const f = makeFakeChild();
    const p = collectChild(f.child);
    f.pushOut('boom');
    f.exit(2);
    const r = await p;
    expect(r.ok).toBe(false);
    expect(r.code).toBe(2);
    expect(r.error).toBeNull();
  });

  it('parse output populates data', async () => {
    const f = makeFakeChild();
    const p = collectChild<{ a: number }>(f.child, { parse: (out) => JSON.parse(out) });
    f.pushOut('{"a":7}');
    f.exit(0);
    expect((await p).data).toEqual({ a: 7 });
  });

  it('parse-with-fallback: a throwing parse yields data=null (not a rejection)', async () => {
    const f = makeFakeChild();
    const p = collectChild(f.child, {
      parse: () => {
        throw new Error('bad');
      },
    });
    f.pushOut('not json');
    f.exit(0);
    const r = await p;
    expect(r.data).toBeNull();
    expect(r.ok).toBe(true); // exit 0 — parse failure does not flip ok
  });

  it('onLine emits complete lines across chunk boundaries + flushes the residual on exit', async () => {
    const f = makeFakeChild();
    const lines: string[] = [];
    const p = collectChild(f.child, { onLine: (l) => lines.push(l) });
    f.pushOut('a\nb'); // 'a' complete, 'b' buffered
    f.pushOut('c\n'); // buffer becomes 'bc', flushed on newline
    f.pushOut('tail'); // no newline — residual
    f.exit(0);
    await p;
    expect(lines).toEqual(['a', 'bc', 'tail']);
  });

  it('spawn error → spawn-failed, code null, ok false, data null, parse not run', async () => {
    const f = makeFakeChild();
    const parse = vi.fn(() => 'x');
    const p = collectChild(f.child, { parse });
    f.fail(new Error('ENOENT'));
    const r = await p;
    expect(r.error).toEqual({ kind: 'spawn-failed', message: 'ENOENT' });
    expect(r.code).toBeNull();
    expect(r.ok).toBe(false);
    expect(r.data).toBeNull();
    expect(parse).not.toHaveBeenCalled();
  });

  it('timeout: SIGTERM, then SIGKILL after the grace, error kind timeout', async () => {
    vi.useFakeTimers();
    try {
      const f = makeFakeChild();
      const p = collectChild(f.child, { timeout: 1000, killGraceMs: 500 });
      vi.advanceTimersByTime(1000);
      expect(f.kills).toEqual(['SIGTERM']);
      vi.advanceTimersByTime(500);
      expect(f.kills).toEqual(['SIGTERM', 'SIGKILL']);
      f.exit(null); // the kill lands
      const r: WikiResult = await p;
      expect(r.ok).toBe(false);
      expect(r.error?.kind).toBe('timeout');
    } finally {
      vi.useRealTimers();
    }
  });

  it('a clean, fast exit does not kill the child', async () => {
    vi.useFakeTimers();
    try {
      const f = makeFakeChild();
      const p = collectChild(f.child, { timeout: 1000 });
      f.exit(0);
      await p;
      vi.advanceTimersByTime(5000); // well past the timeout — timer was cleared
      expect(f.kills).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });
});
