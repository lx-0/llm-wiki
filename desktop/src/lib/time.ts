/** Relative "time ago" — the single source for both the panel and the Browse list,
 *  so the same record reads identically on every surface (was "1h ago" vs "60m"). */
export function fmtAgo(ms: number | null): string {
  if (ms == null) return '—';
  const min = Math.round((Date.now() - ms) / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}
