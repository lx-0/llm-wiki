import { describe, it, expect } from 'vitest';
import { parseTriage } from './triage';

// The record parse + prose scrub live engine-side now (`wiki triage list --json`,
// pinned by tests/test_triage_record_contract.py). This side owns only the
// payload → TriageRecord mapping and the display sort.

const PAYLOAD = JSON.stringify({
  records: [
    {
      stem: '2026-07-11-note', type: 'idea', status: 'pending', kind: 'idea',
      summary: 'Spin up a weekend synth project', source: 'raw/notes/voice/2026-07-11-note.md',
      confidence: 'medium', detected_at: '2026-07-11T20:00:00', date: '2026-07-11',
      detail: 'Accept to capture it.',
    },
    {
      stem: '2026-07-10-bob', type: 'task', status: 'pending', kind: 'action_item',
      summary: 'Reply to Bob about the invoice', source: 'raw/notes/email/2026-07-10-bob.md',
      confidence: 'high', detected_at: '2026-07-10T09:00:00', date: '2026-07-10',
      detail: 'Accept to add it to your tasks.',
    },
    {
      stem: '2026-07-09-x', type: 'note', status: 'dismissed', kind: 'note',
      summary: 'Random passing thought', source: 'raw/notes/voice/2026-07-09-x.md',
      confidence: 'low', detected_at: '2026-07-09T08:00:00', date: '2026-07-09',
      detail: 'Accept to keep it.',
    },
  ],
  pending: 2,
  total: 3,
});

describe('parseTriage', () => {
  it('display-sorts: pending first, task before idea, dismissed last', () => {
    const recs = parseTriage(PAYLOAD);
    expect(recs.map((r) => r.stem)).toEqual(['2026-07-10-bob', '2026-07-11-note', '2026-07-09-x']);
    expect(recs[0].type).toBe('task');
    expect(recs[recs.length - 1].status).toBe('dismissed');
  });

  it('maps every TriageRecord field from the payload', () => {
    const bob = parseTriage(PAYLOAD).find((r) => r.stem === '2026-07-10-bob');
    expect(bob).toEqual({
      stem: '2026-07-10-bob',
      type: 'task',
      status: 'pending',
      summary: 'Reply to Bob about the invoice',
      source: 'raw/notes/email/2026-07-10-bob.md',
      detail: 'Accept to add it to your tasks.',
      date: '2026-07-10',
      confidence: 'high',
    });
  });

  it('returns [] for a payload without a records array', () => {
    expect(parseTriage('{"records": null, "pending": 0, "total": 0}')).toEqual([]);
    expect(parseTriage('{}')).toEqual([]);
  });

  it('drops entries without a stem', () => {
    const noisy = JSON.stringify({ records: [{ type: 'task' }], pending: 1, total: 1 });
    expect(parseTriage(noisy)).toEqual([]);
  });

  it('throws on non-JSON output (runWiki turns that into data=null)', () => {
    expect(() => parseTriage('workspace/inbox/ is empty — nothing to triage.')).toThrow();
  });
});
