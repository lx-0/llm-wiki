// Engine bridge — runs `wiki compile` against the active vault. First action that
// touches the wiki engine (not system data): long-running (Claude SDK, minutes) +
// real cost, so it's spawned async, parses progress from the compiler's output, and
// reports completion. Spawn goes through the shared runWiki runner (vault resolution,
// PATH, ANSI strip, timeout/kill); compile keeps only the single-flight slot + the
// progress scan on top. The engine's flock guards concurrency at the engine level.

import { resolveVault } from './registry';
import { runWiki } from './wiki-exec';

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
export type EngineCommandId = 'update' | 'lint' | 'links' | 'dedup' | 'review' | 'dream';
export const ENGINE_COMMANDS: Record<EngineCommandId, { args: string[]; label: string }> = {
  update: { args: ['update'], label: 'Update app' },
  lint: { args: ['lint', '--structural-only'], label: 'Check for problems' },
  links: { args: ['links'], label: 'Check links' },
  dedup: { args: ['dedup', '--suggest-only'], label: 'Find duplicate pages' },
  review: { args: ['review-wiki'], label: 'Review quality' },
  dream: { args: ['dream'], label: 'Refresh entity pages' },
};

/** Wall-clock cap for any engine command (compile/dream/… can run minutes). Prevents
 *  a wedged child from leaving the single-flight slot occupied forever; the engine's
 *  own SDK/flock guards handle the finer-grained cases. */
const ENGINE_TIMEOUT_MS = 60 * 60 * 1000;

let runningCmd: string | null = null;
let lastProgress: CompileProgress = { current: 0, total: 0 };

export function isCompiling(): boolean {
  return runningCmd === 'compile';
}

/** Whatever engine command is running right now (one at a time), or null. */
export function runningCommand(): string | null {
  return runningCmd;
}

export function currentProgress(): CompileProgress {
  return lastProgress;
}

export interface CompileStart {
  started: boolean;
  running?: boolean;
  error?: string;
}

/** Marker prefix of the engine's structured progress lines
 *  (`wiki compile --progress-json`). */
const PROGRESS_PREFIX = 'PROGRESS ';

/** Scan one output line for progress. Compile runs with `--progress-json`, so its
 *  authoritative signal is the structured `PROGRESS {"current":i,"total":n}` line —
 *  the engine's human log wording is free to change. The human patterns below stay
 *  for the OTHER engine commands (dedup / review / curiosity emit `[i/total]` and
 *  have no structured mode). */
export function scanProgress(line: string): CompileProgress | null {
  if (line.startsWith(PROGRESS_PREFIX)) {
    try {
      const d = JSON.parse(line.slice(PROGRESS_PREFIX.length)) as {
        current?: unknown;
        total?: unknown;
      };
      return { current: Number(d.current) || 0, total: Number(d.total) || 0 };
    } catch {
      return null;
    }
  }
  let m: RegExpMatchArray | null;
  if ((m = line.match(/\[(\d+)\/(\d+)\]/))) {
    return { current: Number(m[1]), total: Number(m[2]) };
  }
  if ((m = line.match(/Files to compile:\s*(\d+)/))) {
    return { current: 0, total: Number(m[1]) };
  }
  if (/Nothing to compile/.test(line)) {
    return { current: 0, total: 0 };
  }
  return null;
}

/** Shared spawn for any `wiki <args>` engine command. One at a time (single-flight).
 *  The spawn/PATH/timeout/kill live in runWiki; this owns the running slot + the
 *  progress scan on top. */
function spawnWiki(
  cmdId: string,
  args: string[],
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  if (runningCmd) return { started: false, running: true };
  const v = resolveVault();
  if (!v) return { started: false, error: 'no vault found' };

  lastProgress = { current: 0, total: 0 };
  runningCmd = cmdId;

  void runWiki(args, {
    timeout: ENGINE_TIMEOUT_MS,
    onLine: (line) => {
      const p = scanProgress(line);
      if (p) {
        lastProgress = p;
        onProgress(lastProgress);
      }
    },
  }).then((r) => {
    runningCmd = null;
    onDone({ ok: r.ok, code: r.code, durationMs: r.durationMs });
  });

  return { started: true };
}

export function startCompile(
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  return spawnWiki('compile', ['compile', '--progress-json'], onProgress, onDone);
}

/** Run any other engine command (update / lint / links / dedup / review). Many
 *  emit `[i/total]` (dedup, review, …) → x/y progress; the rest stay indeterminate. */
export function startEngineCommand(
  id: EngineCommandId,
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  return spawnWiki(id, ENGINE_COMMANDS[id].args, onProgress, onDone);
}

/** Run an arbitrary `wiki <args>` command — used for the engine's own actionable
 *  menu suggestions (e.g. `lint --structural-only`, `dream --all-entities`). The
 *  cmd string from `wiki menu --json` is tokenised on spaces. Curiosity scans,
 *  dedup, and review emit `[i/total]` → x/y progress. */
export function startEngineArgs(
  args: string[],
  onProgress: (p: CompileProgress) => void,
  onDone: (r: CompileResult) => void,
): CompileStart {
  if (args.length === 0) return { started: false, error: 'empty command' };
  return spawnWiki(args.join(' '), args, onProgress, onDone);
}
