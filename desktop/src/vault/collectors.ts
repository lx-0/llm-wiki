// Substrate collectors — `wiki collect --list` (the intake sources: email, calendar,
// meetings, voice, …). Surfaced as a "Sync sources" list so the app can pull from the
// configured accounts, not just ingest URLs. Read on demand (spawns the wiki CLI via
// the shared runWiki runner).

import { runWiki } from './wiki-exec';

export interface Collector {
  name: string;
  configured: boolean;
}

/** ~seconds; a cold uv start is the slow part, the `--list` itself is trivial. */
const COLLECTORS_TIMEOUT_MS = 30_000;

/** Parse the `wiki collect --list` table (already ANSI-stripped). Each data row is
 *  `NAME  ✓/✗  …`; header/divider rows don't match. Header wording is free to change
 *  as long as the NAME + glyph columns stay. */
export function parseCollectors(stdout: string): Collector[] {
  const collectors: Collector[] = [];
  for (const line of stdout.split('\n')) {
    const m = line.match(/^(\S+)\s+(✓|✗)/);
    if (m) collectors.push({ name: m[1], configured: m[2] === '✓' });
  }
  return collectors;
}

export async function listCollectors(): Promise<Collector[]> {
  const r = await runWiki(['collect', '--list'], {
    parse: parseCollectors,
    timeout: COLLECTORS_TIMEOUT_MS,
  });
  return r.data ?? [];
}
