// Substrate collectors — `wiki collect --list --json` (the intake sources: email,
// calendar, meetings, voice, …). Surfaced as a "Sync sources" list so the app can pull
// from the configured accounts, not just ingest URLs. Read on demand (spawns the wiki
// CLI via the shared runWiki runner); the engine's JSON seam replaces the old ✓/✗
// glyph-column scrape, so the human table's wording is free to change.

import { runWiki, parseJson } from './wiki-exec';

export interface Collector {
  name: string;
  configured: boolean;
}

/** ~seconds; a cold uv start is the slow part, the `--list` itself is trivial. */
const COLLECTORS_TIMEOUT_MS = 30_000;

interface RawCollectors {
  collectors?: { name?: unknown; configured?: unknown }[];
}

/** Shape `wiki collect --list --json` into Collector[]. Throws on malformed JSON →
 *  runWiki parse-with-fallback → listCollectors returns []. */
export function parseCollectors(stdout: string): Collector[] {
  const d = parseJson<RawCollectors>(stdout);
  if (!Array.isArray(d.collectors)) return [];
  return d.collectors
    .map((c) => ({ name: String(c.name || ''), configured: c.configured === true }))
    .filter((c) => c.name.length > 0);
}

export async function listCollectors(): Promise<Collector[]> {
  const r = await runWiki(['collect', '--list', '--json'], {
    parse: parseCollectors,
    timeout: COLLECTORS_TIMEOUT_MS,
  });
  return r.data ?? [];
}
