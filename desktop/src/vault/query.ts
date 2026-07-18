// Ask the knowledge base — the headline end-user action. Wraps `wiki query "Q"
// --brief` (cheapest 5-10 line answer) through the shared runWiki runner. Returns the
// answer text; LLM cost applies, so it's request/response (not polled).

import { runWiki } from './wiki-exec';

export interface QueryResult {
  ok: boolean;
  answer: string;
}

/** LLM round-trip for a brief answer — generous cap so a slow model doesn't get cut. */
const QUERY_TIMEOUT_MS = 5 * 60_000;

/** Strip the CLI's leading "wiki query" banner line from an ANSI-stripped answer. */
export function stripQueryBanner(stdout: string): string {
  return stdout.replace(/^\s*wiki query\s*\n/, '').trim();
}

export async function runQuery(question: string): Promise<QueryResult> {
  const q = question.trim();
  if (!q) return { ok: false, answer: '' };

  const r = await runWiki(['query', q, '--brief'], {
    parse: stripQueryBanner,
    timeout: QUERY_TIMEOUT_MS,
  });
  if (r.error?.kind === 'no-vault') return { ok: false, answer: 'No vault found.' };
  if (r.error?.kind === 'spawn-failed') return { ok: false, answer: 'Could not run the query.' };

  const answer = r.data ?? '';
  return {
    ok: r.ok && answer.length > 0,
    answer: answer || r.stderr.trim() || 'No answer.',
  };
}
