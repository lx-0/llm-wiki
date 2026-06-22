// The engine's own actionable home — `wiki menu --json` returns a prioritized list
// of what's pending (entities overdue for dream, edits since last lint, scan
// requests to review, …) plus a status line. We surface this instead of hardcoding
// buttons, so the app stays in sync with whatever the engine thinks needs doing.

import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin } from './wiki-exec';

export interface MenuSuggestion {
  count: number;
  label: string;
  /** raw engine command, e.g. "lint --structural-only" or "dream --all-entities" */
  cmd: string;
  priority: number;
  group: string;
}

export interface MenuResult {
  status: { articles?: number; last_compile_ago?: string; ollama_reachable?: boolean };
  suggestions: MenuSuggestion[];
}

export function getMenu(): Promise<MenuResult | null> {
  return new Promise((resolve) => {
    const v = resolveVault();
    if (!v) return resolve(null);
    let out = '';
    const child = spawn(wikiBin(v.path), ['menu', '--json'], {
      cwd: v.path,
      env: { ...process.env, PATH: augmentedPath() },
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    child.stdout.on('data', (b: Buffer) => (out += b.toString()));
    child.on('error', () => resolve(null));
    child.on('exit', () => {
      try {
        const d = JSON.parse(out);
        const suggestions: MenuSuggestion[] = Array.isArray(d.suggestions)
          ? d.suggestions
              .map((s: Record<string, unknown>) => ({
                count: Number(s.count) || 0,
                label: String(s.label || ''),
                cmd: String(s.cmd || ''),
                priority: Number(s.priority) || 99,
                group: String(s.group || ''),
              }))
              .sort((a: MenuSuggestion, b: MenuSuggestion) => a.priority - b.priority)
          : [];
        resolve({ status: d.status || {}, suggestions });
      } catch {
        resolve(null);
      }
    });
  });
}
