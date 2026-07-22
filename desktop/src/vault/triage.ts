// Triage — the intent inbox (`workspace/inbox/*.md`). Unlike fire-and-forget engine
// commands, triage needs a per-item DECISION (accept / dismiss), so the app lists the
// records via `wiki triage list --json` (the engine serializes the record format —
// frontmatter fields + the scrubbed detail line — so no TypeScript side re-parses
// frontmatter or re-scrubs the record body's template prose) and runs the fast,
// non-interactive `wiki triage accept|dismiss <stem>` subcommands per card.

import { runWiki, parseJson } from './wiki-exec';

export type TriageType = 'task' | 'idea' | 'note';
export interface TriageRecord {
  stem: string;
  type: TriageType | string;
  status: string;
  summary: string;
  source: string; // vault-relative path of the substrate item it was detected from
  detail: string; // human rationale (the triage hint), scrubbed engine-side
  date: string; // capture date, falling back to detected_at (YYYY-MM-DD)
  confidence: string;
}

const TYPE_ORDER: Record<string, number> = { task: 0, idea: 1, note: 2 };

interface RawTriage {
  records?: Record<string, unknown>[];
}

/** Shape `wiki triage list --json` into display-sorted TriageRecords: pending first,
 *  task < idea < note, newest first within a type. Throws on malformed JSON →
 *  runWiki parse-with-fallback → listTriage returns []. */
export function parseTriage(stdout: string): TriageRecord[] {
  const d = parseJson<RawTriage>(stdout);
  if (!Array.isArray(d.records)) return [];
  const records: TriageRecord[] = d.records
    .map((r) => ({
      stem: String(r.stem || ''),
      type: String(r.type || 'note'),
      status: String(r.status || 'pending'),
      summary: String(r.summary || r.stem || ''),
      source: String(r.source || ''),
      detail: String(r.detail || ''),
      date: String(r.date || ''),
      confidence: String(r.confidence || ''),
    }))
    .filter((r) => r.stem.length > 0);
  records.sort((a, b) => {
    if (a.status !== b.status) return a.status === 'pending' ? -1 : 1;
    const t = (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9);
    return t !== 0 ? t : b.stem.localeCompare(a.stem); // newest first within a type
  });
  return records;
}

/** Local read, no LLM; only the uv start costs anything. */
const TRIAGE_LIST_TIMEOUT_MS = 30_000;

/** Read the intent inbox via the engine's JSON seam. Pending-only unless showAll. */
export async function listTriage(showAll = false): Promise<TriageRecord[]> {
  const args = ['triage', 'list', '--json'];
  if (showAll) args.push('--all');
  const r = await runWiki(args, { parse: parseTriage, timeout: TRIAGE_LIST_TIMEOUT_MS });
  return r.data ?? [];
}

/** Fast, non-interactive; only the uv start costs anything. */
const TRIAGE_ACTION_TIMEOUT_MS = 30_000;

/** Run `wiki triage accept|dismiss <stem>` — fast, non-interactive. Async (uv startup). */
export async function triageAction(
  stem: string,
  action: 'accept' | 'dismiss',
): Promise<{ ok: boolean; message: string }> {
  const r = await runWiki(['triage', action, stem], { timeout: TRIAGE_ACTION_TIMEOUT_MS });
  if (r.error?.kind === 'no-vault') return { ok: false, message: 'no vault' };
  if (r.error?.kind === 'spawn-failed') return { ok: false, message: r.error.message };
  return { ok: r.ok, message: `${r.stdout}${r.stderr}`.trim() };
}
