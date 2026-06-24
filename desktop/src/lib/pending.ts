// The engine's `wiki menu --json` labels are written for an operator ("entity pages
// overdue for dream", "sources changed since compile"). Re-phrase the known actions in
// plain English for a non-technical user. Shared by the panel + the cockpit so both
// surfaces speak the same language; the original label stays available on hover.

export interface PendingSuggestion {
  count: number;
  label: string;
  cmd: string;
}

/** A plain action verb for the button, so it's not a bare "Run what?". */
export function pendingVerb(cmd: string): string {
  const verb = cmd.trim().split(/\s+/)[0];
  const map: Record<string, string> = {
    compile: 'Add', 'process-inbox': 'Sort', dream: 'Refresh', 'dream-entity': 'Refresh',
    dedup: 'Review', links: 'Fix', lint: 'Check', 'review-wiki': 'Review', curiosity: 'Explore', flush: 'Save',
  };
  return map[verb] ?? 'Run';
}

export function friendlyPending(s: PendingSuggestion): string {
  const n = s.count || 0;
  const plural = (one: string, many: string) => (n === 1 ? one : many);
  const verb = s.cmd.trim().split(/\s+/)[0];
  const map: Record<string, string> = {
    compile: n ? `${n} new ${plural('source', 'sources')} to add to your wiki` : 'New material to add to your wiki',
    'process-inbox': n ? `${n} new ${plural('capture', 'captures')} to sort` : 'New captures to sort',
    dream: n ? `${n} ${plural('page needs', 'pages need')} refreshing` : 'Pages to refresh',
    'dream-entity': n ? `${n} ${plural('page needs', 'pages need')} refreshing` : 'Pages to refresh',
    dedup: n ? `${n} possible duplicate ${plural('page', 'pages')}` : 'Possible duplicate pages',
    links: n ? `${n} broken ${plural('link', 'links')} to fix` : 'Broken links to fix',
    lint: 'Health check available',
    'review-wiki': 'Quality review available',
    curiosity: n ? `${n} ${plural('question', 'questions')} to explore` : 'Questions to explore',
    flush: 'Save this session to your wiki',
  };
  return map[verb] ?? s.label;
}
