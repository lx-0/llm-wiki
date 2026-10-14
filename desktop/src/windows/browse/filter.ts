// Browse derivations — pure functions over the entry list so the component only renders.

export interface Entry {
  title: string;
  file: string;
  type: string;
  mtimeMs: number;
}

/** Cap the DOM; search narrows it. */
export const MAX_ROWS = 400;

/** Canonical order of the known kinds; unknown kinds follow alphabetically. */
const ORDER = ['person', 'project', 'concept', 'fact', 'area', 'map', 'link', 'note'];

function rank(type: string): number {
  const i = ORDER.indexOf(type);
  return i === -1 ? ORDER.length : i;
}

function byKind(a: string, b: string): number {
  return rank(a) - rank(b) || a.localeCompare(b);
}

/** Substring match on title or path (case-insensitive) plus an exact type filter. */
export function filterEntries(all: readonly Entry[], query: string, type: string): Entry[] {
  const q = query.trim().toLowerCase();
  return all.filter(
    (e) =>
      (!type || e.type === type) &&
      (!q || e.title.toLowerCase().includes(q) || e.file.toLowerCase().includes(q)),
  );
}

export function capRows(rows: readonly Entry[], max = MAX_ROWS): { shown: Entry[]; hidden: number } {
  return { shown: rows.slice(0, max), hidden: Math.max(0, rows.length - max) };
}

/** Distinct kinds present, in canonical order — the filter chips. */
export function typeChips(all: readonly Entry[]): string[] {
  return [...new Set(all.map((e) => e.type))].sort(byKind);
}

/** Per-kind counts of the rows, in canonical order — the footer. */
export function typeCounts(rows: readonly Entry[]): { type: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const e of rows) counts.set(e.type, (counts.get(e.type) ?? 0) + 1);
  return [...counts.entries()].sort(([a], [b]) => byKind(a, b)).map(([type, count]) => ({ type, count }));
}
