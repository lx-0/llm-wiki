// Overview chart derivations — pure functions over the data the window loads.

import { activity } from '../../lib/activity';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export interface AxisDay {
  /** local calendar day as YYYY-MM-DD */
  key: string;
  /** tooltip name — "Wed 14 Oct" */
  name: string;
}

export interface AxisTick {
  index: number;
  label: string;
}

function isoDay(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

/** A Monday closer than this to today loses its tick — the two labels would collide. */
const TICK_CLEARANCE_DAYS = 3;

/** One local calendar day per bin ending today, oldest first, with an axis tick on every
 *  Monday and on today (a Monday within three days of today yields to "Today"). */
export function dayAxis(now: number, days = 30): { days: AxisDay[]; ticks: AxisTick[] } {
  const out: AxisDay[] = [];
  const ticks: AxisTick[] = [];
  const today = new Date(now);
  today.setHours(12, 0, 0, 0);
  for (let i = 0; i < days; i += 1) {
    const ago = days - 1 - i;
    const d = new Date(today);
    d.setDate(today.getDate() - ago);
    out.push({ key: isoDay(d), name: `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}` });
    if (ago === 0) ticks.push({ index: i, label: 'Today' });
    else if (d.getDay() === 1 && ago >= TICK_CLEARANCE_DAYS) {
      ticks.push({ index: i, label: `${d.getDate()} ${MONTHS[d.getMonth()]}` });
    }
  }
  return { days: out, ticks };
}

const NICE = [1, 2, 5, 10];

/** The smallest clean maximum (1 · 2 · 5 × 10ⁿ) at or above the data, and ticks at 0 and max —
 *  never below 1, so an empty month still has a baseline and a top. */
export function columnScale(values: readonly number[]): { max: number; ticks: number[] } {
  const top = Math.max(0, ...values);
  let max = 1;
  if (top > 1) {
    const mag = 10 ** Math.floor(Math.log10(top));
    max = NICE.map((n) => n * mag).find((n) => n >= top) ?? 10 * mag;
  }
  return { max, ticks: [0, max] };
}

/** The entity-type order of the hue wheel in tokens.css — the tie-break for equal counts. */
const KIND_ORDER = ['person', 'project', 'concept', 'fact', 'area', 'map', 'link', 'note'];
const kindRank = (type: string): number => {
  const i = KIND_ORDER.indexOf(type);
  return i < 0 ? KIND_ORDER.length : i;
};

export interface TypeBar {
  type: string;
  count: number;
  /** rounded percent of all entries */
  share: number;
}

/** Notes per type, largest first (ties in the canonical kind order), share as a rounded percent. */
export function typeBars(entries: readonly { type: string }[]): TypeBar[] {
  const counts = new Map<string, number>();
  for (const entry of entries) counts.set(entry.type, (counts.get(entry.type) ?? 0) + 1);
  const total = entries.length;
  return [...counts.entries()]
    .sort(([ta, a], [tb, b]) => b - a || kindRank(ta) - kindRank(tb) || ta.localeCompare(tb))
    .map(([type, count]) => ({ type, count, share: Math.round((count / total) * 100) }));
}

/** Chunks a continuously recording channel writes per hour at the listener's 30 s cadence. */
export const FULL_HOUR_CHUNKS = 120;

/** 0 for nothing, else the quartile of a full hour (1…4), capped at 4. */
export function heatLevel(count: number, full = FULL_HOUR_CHUNKS): number {
  if (count <= 0) return 0;
  return Math.min(4, Math.ceil(count / (full / 4)));
}

const HOUR_MS = 3_600_000;
const TICK_HOURS = new Set([0, 6, 12, 18]);
/** A clock tick closer than this (in bins) to "now" loses its label. */
const NOW_CLEARANCE_BINS = 2;

/** Ticks at local 00 / 06 / 12 / 18 plus "now" on the last bin. */
export function hourTicks(startMs: number, bins: number): AxisTick[] {
  const ticks: AxisTick[] = [];
  for (let i = 0; i < bins; i += 1) {
    const left = bins - 1 - i;
    if (left === 0) {
      ticks.push({ index: i, label: 'now' });
      continue;
    }
    const hour = new Date(startMs + i * HOUR_MS).getHours();
    if (TICK_HOURS.has(hour) && left > NOW_CLEARANCE_BINS) {
      ticks.push({ index: i, label: String(hour).padStart(2, '0') });
    }
  }
  return ticks;
}

const clock = (ms: number): string => `${String(new Date(ms).getHours()).padStart(2, '0')}:00`;

/** The bin's hour range in local time — "14:00–15:00". */
export function hourName(startMs: number, i: number): string {
  return `${clock(startMs + i * HOUR_MS)}–${clock(startMs + (i + 1) * HOUR_MS)}`;
}

export interface StatTile {
  label: string;
  value: string;
}

/** The stat-tile row: label + value, nothing else (a one-number chart is a tile, not a chart). */
export function statTiles(args: {
  entries: readonly { mtimeMs: number }[];
  inbox: number;
  issues: number;
  now: number;
}): StatTile[] {
  const recent = activity(args.entries, args.now);
  return [
    { label: 'Updated today', value: recent.today.toLocaleString() },
    { label: 'This week', value: recent.week.toLocaleString() },
    { label: 'Inbox', value: args.inbox.toLocaleString() },
    { label: 'Issues', value: args.issues.toLocaleString() },
  ];
}
