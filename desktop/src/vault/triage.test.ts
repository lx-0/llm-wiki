import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { listTriage } from './triage';

// Build a throwaway vault + a registry that points at it (resolveVault reads
// $XDG_CONFIG_HOME/llm-wiki/vaults), so listTriage's real fs read + the record-format
// parse/scrub/sort run end-to-end. The record bodies mirror scripts/intents/_record.py
// exactly — this test is the tripwire that catches the engine rephrasing that prose.

let tmp: string;
let prevXdg: string | undefined;

// One record, frontmatter + body, in the exact shape _record.py writes.
function record(opts: {
  type: string;
  status: string;
  summary: string;
  kind: string;
  confidence: string;
  source: string;
  detectedAt: string;
  stem: string;
  hint: string;
}): void {
  const fm = [
    '---',
    `type: ${opts.type}`,
    `status: ${opts.status}`,
    `kind: ${opts.kind}`,
    `confidence: ${opts.confidence}`,
    `summary: ${JSON.stringify(opts.summary)}`,
    `source: ${opts.source}`,
    `detected_at: ${opts.detectedAt}`,
    '---',
  ].join('\n');
  const body =
    `# ${opts.summary}\n\n` +
    `_Detected from [[${opts.stem}]] · ${opts.kind} · confidence ${opts.confidence}. ` +
    `${opts.hint} Set \`status: dismissed\` to drop._\n\n` +
    `## ${opts.type[0].toUpperCase()}${opts.type.slice(1)}\n\n` +
    `${opts.summary}\n`;
  const inbox = path.join(tmp, 'vault', 'workspace', 'inbox');
  fs.writeFileSync(path.join(inbox, `${opts.stem}.md`), `${fm}\n${body}`, 'utf8');
}

beforeAll(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'triage-test-'));
  fs.mkdirSync(path.join(tmp, 'vault', 'workspace', 'inbox'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'config', 'llm-wiki'), { recursive: true });
  fs.writeFileSync(path.join(tmp, 'config', 'llm-wiki', 'vaults'), path.join(tmp, 'vault') + '\n');
  prevXdg = process.env.XDG_CONFIG_HOME;
  process.env.XDG_CONFIG_HOME = path.join(tmp, 'config');

  record({
    type: 'task', status: 'pending', kind: 'action_item', confidence: 'high',
    summary: 'Reply to Bob about the invoice', source: 'raw/notes/email/2026-07-10-bob.md',
    detectedAt: '2026-07-10T09:00:00', stem: '2026-07-10-bob',
    hint: 'Accept to add it to your tasks.',
  });
  record({
    type: 'idea', status: 'pending', kind: 'idea', confidence: 'medium',
    summary: 'Spin up a weekend synth project', source: 'raw/notes/voice/2026-07-11-note.md',
    detectedAt: '2026-07-11T20:00:00', stem: '2026-07-11-note',
    hint: 'Accept to capture it.',
  });
  record({
    type: 'note', status: 'dismissed', kind: 'note', confidence: 'low',
    summary: 'Random passing thought', source: 'raw/notes/voice/2026-07-09-x.md',
    detectedAt: '2026-07-09T08:00:00', stem: '2026-07-09-x',
    hint: 'Accept to keep it.',
  });
});

afterAll(() => {
  if (prevXdg === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = prevXdg;
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('listTriage', () => {
  it('pending-only by default, task before idea', () => {
    const recs = listTriage();
    expect(recs.map((r) => r.stem)).toEqual(['2026-07-10-bob', '2026-07-11-note']);
    expect(recs[0].type).toBe('task');
    expect(recs[1].type).toBe('idea');
  });

  it('scrubs the provenance prefix AND the "Set status: dismissed" CLI instruction from the detail', () => {
    const bob = listTriage().find((r) => r.stem === '2026-07-10-bob');
    expect(bob?.detail).toBe('Accept to add it to your tasks.');
    expect(bob?.detail).not.toMatch(/Detected from/i);
    expect(bob?.detail).not.toMatch(/status/i);
  });

  it('parses frontmatter fields (summary unquoted, date truncated to YYYY-MM-DD)', () => {
    const bob = listTriage().find((r) => r.stem === '2026-07-10-bob');
    expect(bob?.summary).toBe('Reply to Bob about the invoice');
    expect(bob?.source).toBe('raw/notes/email/2026-07-10-bob.md');
    expect(bob?.date).toBe('2026-07-10');
    expect(bob?.confidence).toBe('high');
  });

  it('showAll includes dismissed records, pending still first', () => {
    const all = listTriage(true);
    expect(all.map((r) => r.stem)).toContain('2026-07-09-x');
    expect(all[0].status).toBe('pending');
    expect(all[all.length - 1].status).toBe('dismissed');
  });
});
