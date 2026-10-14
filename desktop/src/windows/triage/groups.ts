// Triage derivations — grouping, ordering and the meta line, kept pure so the component only
// renders. Records come from `wiki triage list --json` via the main process.

export interface TriageRecord {
  stem: string;
  type: string;
  status: string;
  summary: string;
  source: string;
  detail: string;
  date: string;
  confidence: string;
}

export type GroupKey = 'task' | 'idea' | 'note' | 'other';

export interface Group {
  key: GroupKey;
  label: string;
  items: TriageRecord[];
  pending: number;
}

const GROUPS: { key: GroupKey; label: string }[] = [
  { key: 'task', label: 'Tasks' },
  { key: 'idea', label: 'Ideas' },
  { key: 'note', label: 'Notes' },
  { key: 'other', label: 'Other' },
];
const KNOWN = new Set(['task', 'idea', 'note']);
const CONFIDENCE_RANK: Record<string, number> = { low: 0, medium: 1, high: 2 };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function groupOf(record: TriageRecord): GroupKey {
  return KNOWN.has(record.type) ? (record.type as GroupKey) : 'other';
}

/** Tasks → ideas → notes → other, empty groups skipped; within a group the unsure
 *  (low-confidence) items come first, then newest stem first. */
export function groupRecords(records: readonly TriageRecord[]): Group[] {
  return GROUPS.map(({ key, label }) => {
    const items = records
      .filter((r) => groupOf(r) === key)
      .sort(
        (a, b) =>
          (CONFIDENCE_RANK[a.confidence] ?? 1) - (CONFIDENCE_RANK[b.confidence] ?? 1) ||
          b.stem.localeCompare(a.stem),
      );
    return { key, label, items, pending: items.filter((r) => r.status === 'pending').length };
  }).filter((g) => g.items.length > 0);
}

export function pendingCount(records: readonly TriageRecord[]): number {
  return records.filter((r) => r.status === 'pending').length;
}

/** The folder a capture came from ("email", "voice") — or the file stem when the folder is
 *  just a date (`daily/2026-10-13/sessions.md` → "sessions"), since the date is shown anyway. */
function sourceFolder(source: string): string {
  const parts = source.split('/');
  const folder = parts.length >= 2 ? parts[parts.length - 2] : '';
  if (folder && !/^\d{4}-\d{2}-\d{2}$/.test(folder)) return folder;
  return (parts[parts.length - 1] || '').replace(/\.md$/, '');
}

/** Plain words for the engine's substrate folders — "sessions" is an AI coding session, not
 *  the screen/audio capture, and a first-run reader cannot know that from the folder name. */
const SOURCE_NAMES: Record<string, string> = {
  sessions: 'an AI chat',
  voice: 'a voice memo',
  email: 'email',
  calendar: 'your calendar',
  gmeet: 'a meeting',
  screenshots: 'a screenshot',
  pictures: 'a photo',
  browser: 'your browser',
  youtube: 'a video',
  clippings: 'a clipping',
  capture: 'screen capture',
};

function sourceName(source: string): string {
  const folder = sourceFolder(source);
  return SOURCE_NAMES[folder] ?? folder;
}

function shortDate(date: string): string {
  const [, month, day] = date.split('-');
  const name = MONTHS[Number(month) - 1];
  return name ? `${Number(day)} ${name}` : date;
}

/** "from email · 13 Oct", plus the status once the record is resolved. */
export function metaLine(record: TriageRecord): string {
  return [
    record.source ? `from ${sourceName(record.source)}` : '',
    shortDate(record.date),
    record.status !== 'pending' ? record.status : '',
  ]
    .filter(Boolean)
    .join(' · ');
}
