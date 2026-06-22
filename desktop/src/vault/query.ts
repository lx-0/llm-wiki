// Ask the knowledge base — the headline end-user action. Wraps `wiki query "Q"
// --brief` (cheapest 5-10 line answer). Returns the answer text; LLM cost applies,
// so it's request/response (not polled).

import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin, ANSI } from './wiki-exec';

export interface QueryResult {
  ok: boolean;
  answer: string;
}

export function runQuery(question: string): Promise<QueryResult> {
  return new Promise((resolve) => {
    const q = question.trim();
    if (!q) return resolve({ ok: false, answer: '' });
    const v = resolveVault();
    if (!v) return resolve({ ok: false, answer: 'No vault found.' });

    let out = '';
    let err = '';
    const child = spawn(wikiBin(v.path), ['query', q, '--brief'], {
      cwd: v.path,
      env: { ...process.env, PATH: augmentedPath() },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.stdout.on('data', (b: Buffer) => (out += b.toString()));
    child.stderr.on('data', (b: Buffer) => (err += b.toString()));
    child.on('error', () => resolve({ ok: false, answer: 'Could not run the query.' }));
    child.on('exit', (code) => {
      // Strip ANSI + the CLI's leading "wiki query" banner line.
      const answer = out
        .replace(ANSI, '')
        .replace(/^\s*wiki query\s*\n/, '')
        .trim();
      resolve({
        ok: code === 0 && answer.length > 0,
        answer: answer || err.replace(ANSI, '').trim() || 'No answer.',
      });
    });
  });
}
