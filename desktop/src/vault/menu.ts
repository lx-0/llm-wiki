// The engine's own actionable home — `wiki menu --json` returns a prioritized list
// of what's pending (entities overdue for dream, edits since last lint, scan
// requests to review, …) plus a status line. We surface this instead of hardcoding
// buttons, so the app stays in sync with whatever the engine thinks needs doing.
// Goes through the shared runWiki runner.

import { runWiki, parseJson } from './wiki-exec';

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

/** Local, read-only menu build — fast; a cold uv start is the only slow part. */
const MENU_TIMEOUT_MS = 30_000;

interface RawMenu {
  status?: MenuResult['status'];
  suggestions?: Record<string, unknown>[];
}

/** Shape `wiki menu --json` into MenuResult (suggestions sorted by priority). Throws
 *  on malformed JSON → runWiki fallback → getMenu returns null. */
export function parseMenu(stdout: string): MenuResult {
  const d = parseJson<RawMenu>(stdout);
  const suggestions: MenuSuggestion[] = Array.isArray(d.suggestions)
    ? d.suggestions
        .map((s) => ({
          count: Number(s.count) || 0,
          label: String(s.label || ''),
          cmd: String(s.cmd || ''),
          priority: Number(s.priority) || 99,
          group: String(s.group || ''),
        }))
        .sort((a, b) => a.priority - b.priority)
    : [];
  return { status: d.status || {}, suggestions };
}

export async function getMenu(): Promise<MenuResult | null> {
  const r = await runWiki(['menu', '--json'], { parse: parseMenu, timeout: MENU_TIMEOUT_MS });
  return r.data;
}
