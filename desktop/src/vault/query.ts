// Ask the knowledge base — the headline end-user action. Wraps `wiki query "Q"
// --brief --json` (cheapest 5-10 line answer, machine-readable payload) through the
// shared runWiki runner. Returns the answer text; LLM cost applies, so it's
// request/response (not polled).

import { runWiki } from './wiki-exec';

export interface QueryResult {
  ok: boolean;
  answer: string;
}

/** LLM round-trip for a brief answer — generous cap so a slow model doesn't get cut. */
const QUERY_TIMEOUT_MS = 5 * 60_000;

/** Extract the answer from `wiki query --json` stdout. The dispatcher prints its
 *  banner line before the payload, so parse from the first `{` (the banner never
 *  contains one). Throws on malformed/missing JSON → runWiki parse-with-fallback →
 *  data=null. */
export function parseQueryAnswer(stdout: string): string {
  const start = stdout.indexOf('{');
  if (start === -1) throw new Error('no JSON payload in query output');
  const d = JSON.parse(stdout.slice(start)) as { answer?: unknown };
  return typeof d.answer === 'string' ? d.answer.trim() : '';
}

export async function runQuery(question: string): Promise<QueryResult> {
  const q = question.trim();
  if (!q) return { ok: false, answer: '' };

  const r = await runWiki(['query', q, '--brief', '--json'], {
    parse: parseQueryAnswer,
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
