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
