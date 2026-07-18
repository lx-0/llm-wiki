// The one seam between the desktop app and the vault's `wiki` CLI. Every engine
// call goes through runWiki() — it owns vault resolution, PATH augmentation (a
// launchd/Finder-launched app has a minimal PATH: no Homebrew/asdf, and the `wiki`
// wrapper needs `uv`), spawn, stdout/stderr collection, ANSI stripping,
// JSON-parse-with-fallback, a timeout (SIGTERM then SIGKILL), and error
// normalization. The six former spawn sites (compile / collectors / query /
// triage / doctor / menu) collapse to args + a small parse/map on top.
//
// NOTE (behavior-preserving): the engine's output-parsing contracts are exactly as
// today — a later engine-side candidate adds `--json` to the human-text surfaces
// (collect --list, query, compile progress). This file does not scrape; each caller
// still owns its own parse.

import type { EventEmitter } from 'node:events';
import { spawn } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { resolveVault } from './registry';

export function augmentedPath(): string {
  return [
    '/opt/homebrew/bin',
    path.join(os.homedir(), '.local', 'bin'),
    path.join(os.homedir(), '.asdf', 'shims'),
    '/usr/local/bin',
    process.env.PATH || '',
  ].join(':');
}

export function wikiBin(vaultPath: string): string {
  return path.join(vaultPath, '.wiki', 'wiki');
}

/** Strip ANSI escape codes from CLI output before showing it in the UI. */
// eslint-disable-next-line no-control-regex
export const ANSI = /\x1b\[[0-9;]*m/g;

/** Default per-call wall-clock cap. A hung `wiki doctor` (git fetch + network
 *  probes) must not leave a promise pending forever; long commands pass their own. */
export const DEFAULT_TIMEOUT_MS = 60_000;
/** Grace between SIGTERM and the follow-up SIGKILL when a call times out. */
export const KILL_GRACE_MS = 3_000;

export type WikiErrorKind = 'no-vault' | 'spawn-failed' | 'timeout';

export interface WikiError {
  kind: WikiErrorKind;
  message: string;
}

/** Normalized outcome of one `wiki <args>` invocation. `data` is the parse() output
 *  (null when no parse is given, parse threw, or the process never ran). */
export interface WikiResult<T = string> {
  ok: boolean; // exit code 0 (and not timed out / spawn-failed)
  code: number | null; // process exit code; null if killed / never spawned
  stdout: string; // ANSI-stripped
  stderr: string; // ANSI-stripped
  durationMs: number;
  data: T | null;
  error: WikiError | null;
}

export interface RunWikiOptions<T> {
  /** Turn stdout into a typed value. If it throws, `data` falls back to null
   *  (this is the JSON-parse-with-fallback contract doctor/menu rely on). */
  parse?: (stdout: string, result: WikiResult<T>) => T;
  /** Wall-clock cap in ms (default DEFAULT_TIMEOUT_MS). On expiry: SIGTERM, then
   *  SIGKILL after KILL_GRACE_MS. */
  timeout?: number;
  /** Called with each complete line (stdout + stderr) as it arrives — used by
   *  compile for its `[i/total]` progress scan. Residual (no trailing newline) is
   *  flushed once on process exit. */
  onLine?: (line: string) => void;
  /** SIGTERM→SIGKILL grace override (tests). */
  killGraceMs?: number;
}

/** The subset of ChildProcess collectChild drives — kept minimal so tests can pass
 *  a fake EventEmitter-backed child without a real spawn. */
export interface ChildLike {
  readonly stdout: EventEmitter | null;
  readonly stderr: EventEmitter | null;
  on(event: 'exit', listener: (code: number | null) => void): unknown;
  on(event: 'error', listener: (err: Error) => void): unknown;
  kill(signal?: NodeJS.Signals | number): boolean;
}

/** Drive an already-spawned child to a normalized WikiResult. Split out from
 *  runWiki so the collection/strip/parse/timeout/kill logic is unit-testable with a
 *  fake child. */
export function collectChild<T = string>(
  child: ChildLike,
  opts: RunWikiOptions<T> = {},
  startedAt: number = Date.now(),
): Promise<WikiResult<T>> {
  const { parse, timeout = DEFAULT_TIMEOUT_MS, onLine, killGraceMs = KILL_GRACE_MS } = opts;

  return new Promise<WikiResult<T>>((resolve) => {
    let stdout = '';
    let stderr = '';
    let lineBuf = '';
    let settled = false;
    let timedOut = false;
    let killTimer: ReturnType<typeof setTimeout> | null = null;

    const emitLines = (chunk: string): void => {
      if (!onLine) return;
      lineBuf += chunk;
      let nl: number;
      while ((nl = lineBuf.indexOf('\n')) !== -1) {
        onLine(lineBuf.slice(0, nl));
        lineBuf = lineBuf.slice(nl + 1);
      }
    };

    child.stdout?.on('data', (b: Buffer | string) => {
      const s = b.toString();
      stdout += s;
      emitLines(s);
    });
    child.stderr?.on('data', (b: Buffer | string) => {
      const s = b.toString();
      stderr += s;
      emitLines(s);
    });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      killTimer = setTimeout(() => child.kill('SIGKILL'), killGraceMs);
    }, timeout);

    const settle = (code: number | null, spawnErr?: Error): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (killTimer) clearTimeout(killTimer);
      if (onLine && lineBuf) {
        onLine(lineBuf);
        lineBuf = '';
      }
      const outStripped = stdout.replace(ANSI, '');
      const errStripped = stderr.replace(ANSI, '');
      const result: WikiResult<T> = {
        ok: code === 0 && !timedOut && !spawnErr,
        code,
        stdout: outStripped,
        stderr: errStripped,
        durationMs: Date.now() - startedAt,
        data: null,
        error: spawnErr
          ? { kind: 'spawn-failed', message: spawnErr.message }
          : timedOut
            ? { kind: 'timeout', message: `timed out after ${timeout}ms` }
            : null,
      };
      if (parse && !spawnErr) {
        try {
          result.data = parse(outStripped, result);
        } catch {
          result.data = null;
        }
      }
      resolve(result);
    };

    child.on('error', (e: Error) => settle(null, e));
    child.on('exit', (code: number | null) => settle(code));
  });
}

/** Run `wiki <args>` against the active vault and return a normalized result.
 *  Resolves (never rejects): failures are reported via `error` + `ok: false`. */
export function runWiki<T = string>(
  args: string[],
  opts: RunWikiOptions<T> = {},
): Promise<WikiResult<T>> {
  const startedAt = Date.now();
  const v = resolveVault();
  if (!v) {
    return Promise.resolve({
      ok: false,
      code: null,
      stdout: '',
      stderr: '',
      durationMs: 0,
      data: null,
      error: { kind: 'no-vault', message: 'no vault found' },
    });
  }
  const child = spawn(wikiBin(v.path), args, {
    cwd: v.path,
    env: { ...process.env, PATH: augmentedPath() },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  return collectChild<T>(child, opts, startedAt);
}

/** JSON.parse helper for the machine-readable seams (doctor/menu `--json`). Throws
 *  on malformed input, so runWiki's parse-with-fallback turns it into data=null. */
export function parseJson<T>(stdout: string): T {
  return JSON.parse(stdout) as T;
}
