// Section derivations for the panel — which merged actions are "next up", which belong in
// the Tools sheet, how a pasted link maps onto an engine command. Pure, renderer-safe.

import type { Action } from '../../lib/actions';
import type { Collector } from '../../vault/collectors';

/** Pending work in merge order: every row a probe raised (doctor or menu). Pure tools —
 *  rows only the tool catalogue knows — are not work, they live in the Tools sheet. */
export function nextUp(actions: readonly Action[], max = 5): Action[] {
  return actions.filter((action) => action.group !== 'tools').slice(0, max);
}

/** Every tool-backed action once. A tool a probe also raised keeps its counted title, so the
 *  sheet and Next up never show one argv under two phrasings. */
export function toolRows(actions: readonly Action[]): Action[] {
  return actions.filter((action) => action.sources.includes('tool'));
}

const HTTP = /^https?:\/\//i;
const YOUTUBE = /(?:youtube\.com|youtu\.be)\//i;

/** The engine argv for a pasted link, or null when it is not a web link at all. */
export function classifyLink(url: string): string[] | null {
  const link = url.trim();
  if (!HTTP.test(link)) return null;
  return YOUTUBE.test(link) ? ['ingest-youtube', '--url', link] : ['ingest-html', link];
}

/** Modified since the operator last looked (the panel's last close). */
export function isNew(entry: { mtimeMs: number }, seenMs: number): boolean {
  return entry.mtimeMs > seenMs;
}

/** Collectors with an account behind them, in the engine's own order. */
export function configuredSources(collectors: readonly Collector[]): Collector[] {
  return collectors.filter((collector) => collector.configured);
}
