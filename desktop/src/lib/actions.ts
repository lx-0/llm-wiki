// One action model for everything the engine can run on the operator's behalf.
//
// The engine's `wiki doctor --json` (checks with dispatch_args), `wiki menu --json`
// (counted suggestions) and its `tools` list describe overlapping actions; the panel used to
// render them as three independent lists, so one engine action could show up three times with
// three verbs. `mergeActions` folds them into one row per argv, keeping the engine's own
// title/verb verbatim (schema 2 — the engine owns the vocabulary, this file owns the merge).
// Renderer-safe: no Node imports, pure functions only.

export const ACTION_SCHEMA = 2;

export type Severity = 'critical' | 'warning';
export type ActionGroup = 'do' | 'auto' | 'review' | 'tools';
export type ActionSource = 'doctor' | 'menu' | 'tool';

export interface DoctorCheckInput {
  id: string;
  severity: string;
  title: string;
  verb: string | null;
  dispatchArgs?: string[];
}

export interface MenuSuggestionInput {
  id: string;
  count: number;
  title: string;
  verb: string;
  group: string;
  argv: string[];
}

export interface ToolInput {
  id: string;
  title: string;
  verb: string;
  group: string;
  argv: string[];
}

export interface ActionInputs {
  doctor: DoctorCheckInput[];
  menu: MenuSuggestionInput[];
  tools: ToolInput[];
}

export interface Action {
  /** `argv.join(' ')` — the identity used for dedupe and for run-state bookkeeping. */
  key: string;
  id: string;
  title: string;
  verb: string;
  group: ActionGroup;
  argv: string[];
  severity: Severity | null;
  count: number | null;
  sources: ActionSource[];
}

export type RunState = 'idle' | 'running' | 'done' | 'failed';

export interface ActionView extends Action {
  state: RunState;
}

const SEVERITY_RANK: Record<Severity, number> = { critical: 0, warning: 1 };
const GROUP_RANK: Record<ActionGroup, number> = { do: 0, review: 1, auto: 2, tools: 3 };

function asGroup(group: string): ActionGroup {
  return group in GROUP_RANK ? (group as ActionGroup) : 'do';
}

function asSeverity(severity: string): Severity | null {
  return severity === 'critical' || severity === 'warning' ? severity : null;
}

function stronger(a: Severity | null, b: Severity | null): Severity | null {
  if (!a) return b;
  if (!b) return a;
  return SEVERITY_RANK[a] <= SEVERITY_RANK[b] ? a : b;
}

/** Fold doctor checks, menu suggestions and tools into one ordered list, one row per argv. */
export function mergeActions(inputs: ActionInputs): Action[] {
  const rows = new Map<string, Action>();
  const order: string[] = [];

  const upsert = (argv: string[], patch: Partial<Action> & { source: ActionSource }): void => {
    const key = argv.join(' ');
    const existing = rows.get(key);
    if (!existing) {
      rows.set(key, {
        key,
        id: patch.id ?? key,
        title: patch.title ?? key,
        verb: patch.verb ?? 'Run',
        group: patch.group ?? 'do',
        argv: [...argv],
        severity: patch.severity ?? null,
        count: patch.count ?? null,
        sources: [patch.source],
      });
      order.push(key);
      return;
    }
    existing.sources.push(patch.source);
    existing.severity = stronger(existing.severity, patch.severity ?? null);
    // The menu suggestion is the concrete, counted phrasing — it wins the visible fields.
    if (patch.source === 'menu') {
      existing.id = patch.id ?? existing.id;
      existing.title = patch.title ?? existing.title;
      existing.verb = patch.verb ?? existing.verb;
      existing.group = patch.group ?? existing.group;
      existing.count = patch.count ?? existing.count;
    }
  };

  for (const check of inputs.doctor) {
    if (!check.dispatchArgs || check.dispatchArgs.length === 0) continue;
    upsert(check.dispatchArgs, {
      source: 'doctor',
      id: check.id,
      title: check.title,
      verb: check.verb ?? 'Run',
      group: 'do',
      severity: asSeverity(check.severity),
    });
  }
  for (const suggestion of inputs.menu) {
    upsert(suggestion.argv, {
      source: 'menu',
      id: suggestion.id,
      title: suggestion.title,
      verb: suggestion.verb,
      group: asGroup(suggestion.group),
      count: suggestion.count,
    });
  }
  for (const tool of inputs.tools) {
    upsert(tool.argv, { source: 'tool', id: tool.id, title: tool.title, verb: tool.verb, group: 'tools' });
  }

  const position = new Map(order.map((key, index) => [key, index]));
  return [...rows.values()].sort((a, b) => {
    const sa = a.severity ? SEVERITY_RANK[a.severity] : 9;
    const sb = b.severity ? SEVERITY_RANK[b.severity] : 9;
    if (sa !== sb) return sa - sb;
    const ga = a.severity ? -1 : GROUP_RANK[a.group];
    const gb = b.severity ? -1 : GROUP_RANK[b.group];
    if (ga !== gb) return ga - gb;
    return (position.get(a.key) ?? 0) - (position.get(b.key) ?? 0);
  });
}

/** Overlay run state without touching the model: `running` is the key of the command in
 *  flight (or null), `results` maps finished keys to ok/failed. */
export function withRunState(
  actions: readonly Action[],
  running: string | null,
  results: ReadonlyMap<string, boolean>,
): ActionView[] {
  return actions.map((action) => {
    let state: RunState = 'idle';
    if (running === action.key) state = 'running';
    else if (results.has(action.key)) state = results.get(action.key) ? 'done' : 'failed';
    return { ...action, argv: [...action.argv], sources: [...action.sources], state };
  });
}
