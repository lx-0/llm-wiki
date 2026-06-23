// Triage — the intent inbox (`workspace/inbox/*.md`). Unlike fire-and-forget engine
// commands, triage needs a per-item DECISION (accept / dismiss), so the app reads the
// records directly (system data, like status/list) and runs the fast, non-interactive
// `wiki triage accept|dismiss <stem>` subcommands per card. No stdin involved.

import * as fs from 'node:fs';
import * as path from 'node:path';
import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin, ANSI } from './wiki-exec';

export type TriageType = 'task' | 'idea' | 'note';
export interface TriageRecord {
  stem: string;
  type: TriageType | string;
  status: string;
  summary: string;
  source: string;
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
    try {
      const txt = fs.readFileSync(path.join(dir, f), 'utf8');
      const m = txt.match(/^---\r?\n([\s\S]*?)\r?\n---/);
      if (!m) continue;
      fm = m[1];
    } catch {
      continue;
    }
    const status = field(fm, 'status') || 'pending';
    if (!showAll && status !== 'pending') continue;
    records.push({
      stem: f.replace(/\.md$/, ''),
      type: field(fm, 'type') || 'note',
      status,
      summary: field(fm, 'summary') || f.replace(/\.md$/, ''),
      source: field(fm, 'source'),
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

/** Run `wiki triage accept|dismiss <stem>` — fast, non-interactive. Async (uv startup). */
export function triageAction(stem: string, action: 'accept' | 'dismiss'): Promise<{ ok: boolean; message: string }> {
  return new Promise((resolve) => {
    const v = resolveVault();
    if (!v) return resolve({ ok: false, message: 'no vault' });
    let out = '';
    const child = spawn(wikiBin(v.path), ['triage', action, stem], {
      cwd: v.path,
      env: { ...process.env, PATH: augmentedPath() },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.stdout.on('data', (b: Buffer) => (out += b.toString()));
    child.stderr.on('data', (b: Buffer) => (out += b.toString()));
    child.on('error', (e) => resolve({ ok: false, message: e.message }));
    child.on('exit', (code) => resolve({ ok: code === 0, message: out.replace(ANSI, '').trim() }));
  });
}
