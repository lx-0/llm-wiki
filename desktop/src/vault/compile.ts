// Engine bridge — runs `wiki compile` against the active vault. This is the FIRST
// action that touches the wiki engine (not system data): long-running (Claude SDK,
// minutes) + real cost, so it's spawned async and reported on completion. Spawn the
// vault's own `wiki` wrapper (handles uv/venv); the engine's flock guards concurrency.

import { spawn, type ChildProcess } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { resolveVault } from './registry';

export interface CompileResult {
  ok: boolean;
  code: number | null;
  durationMs: number;
}

let proc: ChildProcess | null = null;
let startedAt = 0;

export function isCompiling(): boolean {
  return proc !== null;
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

export function startCompile(onDone: (r: CompileResult) => void): CompileStart {
  if (proc) return { started: false, running: true };
  const v = resolveVault();
  if (!v) return { started: false, error: 'no vault found' };

  const wiki = path.join(v.path, '.wiki', 'wiki');
  startedAt = Date.now();
  const child = spawn(wiki, ['compile'], {
    cwd: v.path,
    env: { ...process.env, PATH: augmentedPath() },
    stdio: 'ignore', // exit code is enough for the MVP; streaming progress is a later nicety
  });
  proc = child;

  const finish = (code: number | null) => {
    if (proc !== child) return; // already finalized
    proc = null;
    onDone({ ok: code === 0, code, durationMs: Date.now() - startedAt });
  };
  child.on('exit', finish);
  child.on('error', () => finish(null));

  return { started: true };
}
