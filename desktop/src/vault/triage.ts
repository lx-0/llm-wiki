// Triage — the intent inbox (`workspace/inbox/*.md`). Unlike fire-and-forget engine
// commands, triage needs a per-item DECISION (accept / dismiss), so the app reads the
// records directly (system data, like status/list) and runs the fast, non-interactive
// `wiki triage accept|dismiss <stem>` subcommands per card. No stdin involved.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { resolveVault } from './registry';
import { runWiki } from './wiki-exec';

export type TriageType = 'task' | 'idea' | 'note';
export interface TriageRecord {
  stem: string;
  type: TriageType | string;
  status: string;
  summary: string;
  source: string; // vault-relative path of the substrate item it was detected from
  detail: string; // human rationale from the record body
  date: string; // detected_at (YYYY-MM-DD)
  confidence: string;
}

const TYPE_ORDER: Record<string, number> = { task: 0, idea: 1, note: 2 };

function field(fm: string, key: string): string {
  const m = fm.match(new RegExp(`^${key}:\\s*(.*)$`, 'm'));
  if (!m) return '';
  return m[1].trim().replace(/^["']|["']$/g, '');
}

/** Read the intent inbox. Pending-only unless showAll. Direct fs read — no spawn. */
export function listTriage(showAll = false): TriageRecord[] {
  const v = resolveVault();
  if (!v) return [];
  const dir = path.join(v.path, 'workspace', 'inbox');
  let files: string[];
  try {
    files = fs.readdirSync(dir).filter((f) => f.endsWith('.md'));
  } catch {
    return [];
  }
  const records: TriageRecord[] = [];
  for (const f of files) {
    let fm = '';
    let body = '';
    try {
      const txt = fs.readFileSync(path.join(dir, f), 'utf8');
      const m = txt.match(/^---\r?\n([\s\S]*?)\r?\n---/);
      if (!m) continue;
      fm = m[1];
      body = txt.slice(m[0].length);
    } catch {
      continue;
    }
    const status = field(fm, 'status') || 'pending';
    if (!showAll && status !== 'pending') continue;
    // rationale: first body paragraph, minus the provenance prefix + CLI instruction
    const para = body.replace(/^\s*#[^\n]*\n/, '').trim().split(/\n\s*\n/)[0] || '';
    const detail = para
      .replace(/Detected from[^.]*\.\s*/i, '')
      .replace(/\s*Set\s+`?status.*$/is, '')
      .replace(/\[\[([^\]]+)\]\]/g, (_m, p: string) => p.split('|')[0])
      .replace(/[_*`]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 240);
    records.push({
      stem: f.replace(/\.md$/, ''),
      type: field(fm, 'type') || 'note',
      status,
      summary: field(fm, 'summary') || f.replace(/\.md$/, ''),
      source: field(fm, 'source'),
      detail,
      date: (field(fm, 'detected_at') || '').slice(0, 10),
      confidence: field(fm, 'confidence'),
    });
  }
  records.sort((a, b) => {
    if (a.status !== b.status) return a.status === 'pending' ? -1 : 1;
    const t = (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9);
    return t !== 0 ? t : b.stem.localeCompare(a.stem); // newest first within a type
  });
  return records;
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
