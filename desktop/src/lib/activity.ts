// Day-level activity over knowledge entries — shared by the panel's status strip and the
// Overview. Counting is by LOCAL calendar day and by mtime: a note the dream cycle refreshed
// counts as updated that day, which is why every label says "updated", never "added".

export interface Dated {
  mtimeMs: number;
}

const DAY_MS = 86_400_000;

/** Whole local calendar days between a timestamp's day and `now`'s day (0 = today, negative
 *  for a timestamp after today). */
export function daysAgo(ms: number, now: number): number {
  const a = new Date(ms);
  const b = new Date(now);
  const utcA = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const utcB = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.round((utcB - utcA) / DAY_MS);
}

/** Entries updated per local day, oldest bucket first, today last. */
export function countPerDay(entries: readonly Dated[], now: number, days = 14): number[] {
  const counts = new Array<number>(days).fill(0);
  for (const entry of entries) {
    const ago = daysAgo(entry.mtimeMs, now);
    if (ago >= 0 && ago < days) counts[days - 1 - ago] += 1;
  }
  return counts;
}

/** Updated today and within the last seven local days (today included). */
export function activity(entries: readonly Dated[], now: number): { today: number; week: number } {
  let today = 0;
  let week = 0;
  for (const entry of entries) {
    const ago = daysAgo(entry.mtimeMs, now);
    if (ago === 0) today += 1;
    if (ago >= 0 && ago < 7) week += 1;
  }
  return { today, week };
}
