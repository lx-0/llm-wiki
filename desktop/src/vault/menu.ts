// The engine's own actionable home — `wiki menu --json` (schema 2) returns the prioritized
// suggestions with the engine's plain-English title + verb + argv, plus the always-available
// tools and a status line. The app renders these verbatim (core/actions.py owns the
// vocabulary) and refuses payloads whose schema it does not know. Goes through the shared
// runWiki runner.

import { ACTION_SCHEMA, type MenuSuggestionInput, type ToolInput } from '../lib/actions';
import { parseJson, runWiki } from './wiki-exec';

export interface MenuSuggestion extends MenuSuggestionInput {
  /** operator-term label (what the TUI prints); the GUI shows `title` */
  label: string;
  priority: number;
}

export type MenuTool = ToolInput;

export interface MenuResult {
  status: { articles?: number; last_compile_ago?: string; ollama_reachable?: boolean };
  suggestions: MenuSuggestion[];
  tools: MenuTool[];
}

/** Local, read-only menu build — fast; a cold uv start is the only slow part. */
const MENU_TIMEOUT_MS = 30_000;

interface RawMenu {
  schema?: unknown;
  status?: MenuResult['status'];
  suggestions?: Record<string, unknown>[];
  tools?: Record<string, unknown>[];
}

function argvOf(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function toSuggestion(raw: Record<string, unknown>): MenuSuggestion | null {
  const argv = argvOf(raw.argv);
  if (argv.length === 0) return null;
  return {
    id: String(raw.id || argv.join(' ')),
    count: Number(raw.count) || 0,
    label: String(raw.label || ''),
    title: String(raw.title || raw.label || argv.join(' ')),
    verb: String(raw.verb || 'Run'),
    group: String(raw.group || 'do'),
    argv,
    priority: Number(raw.priority) || 99,
  };
}

function toTool(raw: Record<string, unknown>): MenuTool | null {
  const argv = argvOf(raw.argv);
  if (argv.length === 0) return null;
  return {
    id: String(raw.id || argv.join(' ')),
    title: String(raw.title || argv.join(' ')),
    verb: String(raw.verb || 'Run'),
    group: 'tools',
    argv,
  };
}

/** Shape `wiki menu --json` into MenuResult (suggestions sorted by priority). Throws on
 *  malformed JSON → runWiki fallback → getMenu returns null. An unknown schema yields empty
 *  lists + a warning rather than a guess. */
export function parseMenu(stdout: string): MenuResult {
  const d = parseJson<RawMenu>(stdout);
  const status = d.status || {};
  if (d.schema !== ACTION_SCHEMA) {
    console.warn(
      `wiki menu --json: unsupported schema ${String(d.schema)} (app expects ${ACTION_SCHEMA}) — run \`wiki update\``,
    );
    return { status, suggestions: [], tools: [] };
  }
  const suggestions = (Array.isArray(d.suggestions) ? d.suggestions : [])
    .map(toSuggestion)
    .filter((s): s is MenuSuggestion => s !== null)
    .sort((a, b) => a.priority - b.priority);
  const tools = (Array.isArray(d.tools) ? d.tools : []).map(toTool).filter((t): t is MenuTool => t !== null);
  return { status, suggestions, tools };
}

export async function getMenu(): Promise<MenuResult | null> {
  const r = await runWiki(['menu', '--json'], { parse: parseMenu, timeout: MENU_TIMEOUT_MS });
  return r.data;
}
