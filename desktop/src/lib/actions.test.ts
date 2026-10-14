import { describe, expect, it } from 'vitest';
import { ACTION_SCHEMA, type ActionInputs, mergeActions, withRunState } from './actions';

const inputs = (over: Partial<ActionInputs> = {}): ActionInputs => ({
  doctor: [],
  menu: [],
  tools: [],
  ...over,
});

describe('mergeActions', () => {
  it('pins the schema the model understands', () => {
    expect(ACTION_SCHEMA).toBe(2);
  });

  it('collapses the same argv from menu and tools into one row with the counted title', () => {
    const rows = mergeActions(
      inputs({
        menu: [
          {
            id: 'dream-sweep',
            count: 12,
            title: '12 pages need refreshing',
            verb: 'Refresh',
            group: 'auto',
            argv: ['dream', '--all-entities'],
          },
        ],
        tools: [
          {
            id: 'dream-sweep',
            title: 'Refresh people & project pages',
            verb: 'Refresh',
            group: 'tools',
            argv: ['dream', '--all-entities'],
          },
        ],
      }),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      key: 'dream --all-entities',
      title: '12 pages need refreshing',
      verb: 'Refresh',
      group: 'auto',
      count: 12,
      severity: null,
      sources: ['menu', 'tool'],
    });
  });

  it('takes severity from the doctor and title from the menu when both share an argv', () => {
    const rows = mergeActions(
      inputs({
        doctor: [
          {
            id: 'compile-state',
            severity: 'warning',
            title: "Your wiki hasn't been updated in 40 days",
            verb: 'Add',
            dispatchArgs: ['compile'],
          },
        ],
        menu: [
          {
            id: 'compile',
            count: 4,
            title: '4 new sources to add to your wiki',
            verb: 'Add',
            group: 'do',
            argv: ['compile'],
          },
        ],
      }),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      title: '4 new sources to add to your wiki',
      severity: 'warning',
      count: 4,
      sources: ['doctor', 'menu'],
    });
  });

  it('drops doctor checks without dispatch args — they are health information, not actions', () => {
    const rows = mergeActions(
      inputs({
        doctor: [
          { id: 'claude-authed', severity: 'critical', title: 'Sign in to Claude', verb: null },
          {
            id: 'hooks-installed',
            severity: 'warning',
            title: 'Session capture isn’t installed',
            verb: 'Install',
            dispatchArgs: ['hooks', 'install'],
          },
        ],
      }),
    );
    expect(rows.map((r) => r.id)).toEqual(['hooks-installed']);
  });

  it('orders critical, warning, then do → review → auto, then tools, each in engine order', () => {
    const rows = mergeActions(
      inputs({
        doctor: [
          { id: 'w', severity: 'warning', title: 'W', verb: 'Fix', dispatchArgs: ['w'] },
          { id: 'c', severity: 'critical', title: 'C', verb: 'Fix', dispatchArgs: ['c'] },
        ],
        menu: [
          { id: 'a1', count: 1, title: 'A1', verb: 'Run', group: 'auto', argv: ['a1'] },
          { id: 'd1', count: 1, title: 'D1', verb: 'Run', group: 'do', argv: ['d1'] },
          { id: 'r1', count: 1, title: 'R1', verb: 'Run', group: 'review', argv: ['r1'] },
          { id: 'd2', count: 1, title: 'D2', verb: 'Run', group: 'do', argv: ['d2'] },
        ],
        tools: [
          { id: 't2', title: 'T2', verb: 'Run', group: 'tools', argv: ['t2'] },
          { id: 't1', title: 'T1', verb: 'Run', group: 'tools', argv: ['t1'] },
        ],
      }),
    );
    expect(rows.map((r) => r.id)).toEqual(['c', 'w', 'd1', 'd2', 'r1', 'a1', 't2', 't1']);
  });
});

describe('withRunState', () => {
  const base = mergeActions(
    inputs({
      tools: [
        {
          id: 'lint',
          title: 'Check for problems',
          verb: 'Check',
          group: 'tools',
          argv: ['lint', '--structural-only'],
        },
        {
          id: 'dedup',
          title: 'Find duplicate pages',
          verb: 'Review',
          group: 'tools',
          argv: ['dedup', '--suggest-only'],
        },
      ],
    }),
  );

  it('marks the running row and keeps everything else idle', () => {
    const view = withRunState(base, 'lint --structural-only', new Map());
    expect(view.map((v) => [v.id, v.state])).toEqual([
      ['lint', 'running'],
      ['dedup', 'idle'],
    ]);
  });

  it('marks finished rows done or failed from the results map', () => {
    const results = new Map([
      ['lint --structural-only', true],
      ['dedup --suggest-only', false],
    ]);
    const view = withRunState(base, null, results);
    expect(view.map((v) => v.state)).toEqual(['done', 'failed']);
  });

  it('never mutates the input rows', () => {
    const before = JSON.stringify(base);
    withRunState(base, 'lint --structural-only', new Map([['dedup --suggest-only', true]]));
    expect(JSON.stringify(base)).toBe(before);
  });
});
