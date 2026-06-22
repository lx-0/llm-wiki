// Engine bridge — runs `wiki compile` against the active vault. First action that
// touches the wiki engine (not system data): long-running (Claude SDK, minutes) +
// real cost, so it's spawned async, parses progress from the compiler's output, and
// reports completion. Spawn the vault's own `wiki` wrapper (handles uv/venv); the
// engine's flock guards concurrency.

import { spawn, type ChildProcess } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { resolveVault } from './registry';

export interface CompileResult {
  ok: boolean;
  code: number | null;
  durationMs: number;
}

export interface CompileProgress {
  current: number;
  total: number;
}

let proc: ChildProcess | null = null;
let startedAt = 0;
let lastProgress: CompileProgress = { current: 0, total: 0 };

export function isCompiling(): boolean {
  return proc !== null;
}

export function currentProgress(): CompileProgress {
  return lastProgress;
}

/** uv/electron-spawn PATH fix — a launchd/Finder-launched app has a minimal PATH
 *  (no Homebrew/asdf), and the `wiki` wrapper needs `uv`. */
function augmentedPath(): string {
  const extra = [
    '/opt/homebrew/bin',
    path.join(os.homedir(), '.local', 'bin'),
    path.join(os.homedir(), '.asdf', 'shims'),
    '/usr/local/bin',
  ];
  return [...extra, process.env.PATH || ''].join(':');
}

export interface CompileStart {
  started: boolean;
  running?: boolean;
  error?: string;
}

export function startCompile(
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  if (proc) return { started: false, running: true };
  const v = resolveVault();
  if (!v) return { started: false, error: 'no vault found' };

  const wiki = path.join(v.path, '.wiki', 'wiki');
  startedAt = Date.now();
  lastProgress = { current: 0, total: 0 };

  const child = spawn(wiki, ['compile'], {
    cwd: v.path,
    env: { ...process.env, PATH: augmentedPath() },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  proc = child;

  // compile.py logs: "Files to compile: N", then per-file "[idx/total]",
  // and "Nothing to compile" on a no-op. (ANSI codes around the text don't matter.)
  const scan = (buf: Buffer) => {
    for (const line of buf.toString().split('\n')) {
      let m: RegExpMatchArray | null;
      if ((m = line.match(/\[(\d+)\/(\d+)\]/))) {
        lastProgress = { current: Number(m[1]), total: Number(m[2]) };
        onProgress(lastProgress);
      } else if ((m = line.match(/Files to compile:\s*(\d+)/))) {
        lastProgress = { current: 0, total: Number(m[1]) };
        onProgress(lastProgress);
      } else if (/Nothing to compile/.test(line)) {
        lastProgress = { current: 0, total: 0 };
        onProgress(lastProgress);
      }
    }
  };
  child.stdout?.on('data', scan);
  child.stderr?.on('data', scan);

  const finish = (code: number | null) => {
    if (proc !== child) return;
    proc = null;
    onDone({ ok: code === 0, code, durationMs: Date.now() - startedAt });
  };
  child.on('exit', finish);
  child.on('error', () => finish(null));

  return { started: true };
}
