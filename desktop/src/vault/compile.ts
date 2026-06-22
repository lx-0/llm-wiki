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

/** Engine commands the app can run (besides compile). Safe + $0 where possible:
 *  `--suggest-only` dedup (no destructive merge), `--structural-only` lint ($0). */
export type EngineCommandId = 'update' | 'lint' | 'links' | 'dedup' | 'review';
export const ENGINE_COMMANDS: Record<EngineCommandId, { args: string[]; label: string }> = {
  update: { args: ['update'], label: 'Update app' },
  lint: { args: ['lint', '--structural-only'], label: 'Check for problems' },
  links: { args: ['links'], label: 'Check links' },
  dedup: { args: ['dedup', '--suggest-only'], label: 'Find duplicate pages' },
  review: { args: ['review-wiki'], label: 'Review quality' },
};

let proc: ChildProcess | null = null;
let runningCmd: 'compile' | EngineCommandId | null = null;
let startedAt = 0;
let lastProgress: CompileProgress = { current: 0, total: 0 };

export function isCompiling(): boolean {
  return runningCmd === 'compile';
}

/** Whatever engine command is running right now (one at a time), or null. */
export function runningCommand(): 'compile' | EngineCommandId | null {
  return runningCmd;
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

/** Shared spawn for any `wiki <args>` engine command. One at a time. */
function spawnWiki(
  cmdId: 'compile' | EngineCommandId,
  args: string[],
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  if (proc) return { started: false, running: true };
  const v = resolveVault();
  if (!v) return { started: false, error: 'no vault found' };

  const wiki = path.join(v.path, '.wiki', 'wiki');
  startedAt = Date.now();
  lastProgress = { current: 0, total: 0 };

  const child = spawn(wiki, args, {
    cwd: v.path,
    env: { ...process.env, PATH: augmentedPath() },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  proc = child;
  runningCmd = cmdId;

  // compile.py logs: "Files to compile: N", then per-file "[idx/total]",
  // "Nothing to compile" on a no-op. (Only compile emits x/y; others stay indeterminate.)
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
    runningCmd = null;
    onDone({ ok: code === 0, code, durationMs: Date.now() - startedAt });
  };
  child.on('exit', finish);
  child.on('error', () => finish(null));

  return { started: true };
}

export function startCompile(
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  return spawnWiki('compile', ['compile'], onProgress, onDone);
}

/** Run any other engine command (update / lint / links / dedup / review). No x/y
 *  progress — the UI shows an indeterminate state until done. */
export function startEngineCommand(id: EngineCommandId, onDone: (r: CompileResult) => void): CompileStart {
  return spawnWiki(id, ENGINE_COMMANDS[id].args, () => {}, onDone);
}
