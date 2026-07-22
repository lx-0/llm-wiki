import { describe, it, expect } from 'vitest';
import { scanProgress } from './compile';

describe('scanProgress', () => {
  it('parses the structured PROGRESS line (wiki compile --progress-json)', () => {
    expect(scanProgress('PROGRESS {"current": 3, "total": 12}')).toEqual({
      current: 3,
      total: 12,
    });
    expect(scanProgress('PROGRESS {"current": 0, "total": 0}')).toEqual({
      current: 0,
      total: 0,
    });
  });

  it('returns null for a malformed PROGRESS line', () => {
    expect(scanProgress('PROGRESS {not json')).toBeNull();
  });

  it('still scans the human [i/total] pattern (dedup / review have no structured mode)', () => {
    expect(scanProgress('[4/17] [email] raw/notes/email/x.md')).toEqual({
      current: 4,
      total: 17,
    });
  });

  it('maps "Files to compile: N" and "Nothing to compile" log lines', () => {
    expect(scanProgress('Files to compile: 9')).toEqual({ current: 0, total: 9 });
    expect(scanProgress('Nothing to compile — all files up to date.')).toEqual({
      current: 0,
      total: 0,
    });
  });

  it('ignores unrelated lines', () => {
    expect(scanProgress('  maintenance: 0 due — queues current')).toBeNull();
  });
});
