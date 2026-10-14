// Fixture payloads for the screenshot harness — one set per named state. Shapes mirror the
// preload contracts in src/{vault,listeners,panel,app}/ipc.ts; keep them in sync by hand
// (the harness is the first thing that breaks when a contract changes, which is the point).

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const TITLES = {
  person: [
    'Sid Rahman',
    'Jana Koch',
    'Tom Becker',
    'Mara Vogt',
    'Lukas Hahn',
    'Nils Berg',
    'Eva Lind',
    'Omar Said',
  ],
  project: [
    'llm-wiki',
    'Township OS',
    'Fleet',
    'Paperclip',
    'meinkontext',
    'Yesterday Cloud',
    'Screenpipe capture',
    'LiteLLM gateway',
  ],
  concept: [
    'Compile pipeline',
    'Dream cycle',
    'Curiosity requests',
    'Piggyback scheduling',
    'Folder index',
    'Wikilink relativization',
    'Seed overlays',
    'Flush pipeline',
    'Vault guard',
    'Token ledger',
    'Entity pages',
    'Intent inbox',
  ],
  fact: [
    'Vault venv lives outside iCloud',
    'kcma-d8 runs Ollama',
    'Gmail account is multi-tenant',
    'Engine pulls from local repo',
  ],
  area: ['Knowledge engineering', 'Home lab', 'Consulting', 'Health'],
  map: ['Engine MOC', 'People MOC', 'Infra MOC'],
  link: ['Dream ↔ Compile', 'Capture ↔ Triage'],
  note: ['Untitled note'],
};
const AGES = [
  12 * MIN,
  40 * MIN,
  3 * HOUR,
  9 * HOUR,
  26 * HOUR,
  2 * DAY,
  4 * DAY,
  9 * DAY,
  20 * DAY,
  45 * DAY,
  80 * DAY,
  120 * DAY,
];

function entries(now) {
  const out = [];
  let i = 0;
  for (const [type, titles] of Object.entries(TITLES)) {
    titles.forEach((title, n) => {
      out.push({
        title,
        file: `knowledge/${type}s/${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.md`,
        type,
        mtimeMs: now - AGES[(i + n) % AGES.length],
      });
      i += 1;
    });
  }
  // Newest first, then one distinct age per rank — a Recent list of five "12m ago" rows
  // reads like a bug in a screenshot. Beyond the twelve ages, each lap is half a year older.
  return out
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .map((entry, rank) => ({
      ...entry,
      mtimeMs: now - AGES[rank % AGES.length] - Math.floor(rank / AGES.length) * 180 * DAY,
    }));
}

/** 24 hourly bins ending at the current hour: a workday of ~120 chunks per channel and hour
 *  (the live 30 s cadence), a lunch gap, nothing overnight. */
function timeline(now) {
  const end = new Date(now);
  end.setMinutes(0, 0, 0);
  const startMs = end.getTime() - 23 * HOUR;
  const mic = [];
  const system = [];
  for (let i = 0; i < 24; i += 1) {
    const h = new Date(startMs + i * HOUR).getHours();
    const on = (h >= 8 && h <= 12) || (h >= 14 && h <= 18);
    mic.push(on ? 112 + ((i * 7) % 9) : 0);
    system.push(on ? (h >= 14 ? 96 + ((i * 5) % 11) : 118 - ((i * 3) % 7)) : 0);
  }
  return { startMs, bucketMs: HOUR, mic, system };
}

const ANSWER =
  '**Sid** owns the Fleet onboarding track. The last two syncs ([[knowledge/people/sid-rahman|Sid Rahman]], ' +
  '[[knowledge/projects/fleet|Fleet]]) agreed on a Thursday deadline for the deck; the open blocker is the ' +
  'LiteLLM gateway key rotation ([[knowledge/concepts/token-ledger]]).';

function base(now) {
  const list = entries(now);
  return {
    vault: {
      status: {
        name: 'lxw',
        path: '/Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw',
        articleCount: 2024,
        lastActivityMs: now - 35 * MIN,
        recent: list.slice(0, 5),
        accessible: true,
      },
      list,
      preview: (file) =>
        `Compiled 2026-10-13 from 3 sources · ${file}\n\nA short body preview of the entry so the detail card has something to show.`,
      collectors: [
        'email',
        'calendar',
        'voice',
        'gmeet',
        'health',
        'screenshots',
        'browser',
        'youtube',
        'capture',
      ].map((name) => ({
        name,
        configured: name !== 'browser',
      })),
      triage: [
        {
          stem: '2026-10-13-call-sid',
          type: 'task',
          status: 'pending',
          summary: 'Call Sid about the Fleet onboarding deck before Thursday',
          source: 'daily/2026-10-13/sessions.md',
          detail: '',
          date: '2026-10-13',
          confidence: 'high',
        },
        {
          stem: '2026-10-13-invoice',
          type: 'task',
          status: 'pending',
          summary: 'Send the September invoice to Township',
          source: 'raw/notes/email/gmail-2026-10-13.md',
          detail: '',
          date: '2026-10-13',
          confidence: 'medium',
        },
        {
          stem: '2026-10-12-dream-dedupe',
          type: 'idea',
          status: 'pending',
          summary: 'Let the dream cycle merge near-duplicate people pages automatically',
          source: 'daily/2026-10-12/voice.md',
          detail: '',
          date: '2026-10-12',
          confidence: 'low',
        },
        {
          stem: '2026-10-12-nas',
          type: 'idea',
          status: 'pending',
          summary: 'Mirror the vault to the NAS nightly',
          source: 'daily/2026-10-12/sessions.md',
          detail: '',
          date: '2026-10-12',
          confidence: 'high',
        },
        {
          stem: '2026-10-11-quote',
          type: 'note',
          status: 'pending',
          summary: '“Substrat und Destillat gehören zusammen” — keep as a design principle',
          source: 'daily/2026-10-11/voice.md',
          detail: '',
          date: '2026-10-11',
          confidence: 'medium',
        },
        {
          stem: '2026-10-10-done',
          type: 'task',
          status: 'accepted',
          summary: 'Rotate the Infisical token',
          source: 'daily/2026-10-10/sessions.md',
          detail: '',
          date: '2026-10-10',
          confidence: 'high',
        },
      ],
      doctor: {
        issues: 3,
        updateAvailable: true,
        updateMessage: 'engine 0.5.4 → 0.5.5',
        checks: [
          {
            id: 'hooks-installed',
            severity: 'warning',
            message: 'no wiki hooks installed in user or project scope — session capture won’t fire',
            title: 'Session capture isn’t installed',
            verb: 'Install',
            fix: 'wiki hooks install',
            dispatchArgs: ['hooks', 'install'],
          },
          {
            id: 'index-drift',
            severity: 'critical',
            message: 'knowledge/index.md drift: 3 duplicate / 2 dangling / 4 missing row(s)',
            title: 'The note index is out of sync',
            verb: 'Rebuild',
            fix: 'wiki reindex',
            dispatchArgs: ['reindex'],
          },
          {
            id: 'ollama-reachable',
            severity: 'warning',
            message: 'Ollama unreachable at 192.168.2.42:11434',
            title: 'Ollama unreachable at 192.168.2.42:11434',
            verb: null,
            fix: 'check kcma-d8 is up',
          },
        ],
      },
      query: { ok: true, answer: ANSWER },
      menu: {
        status: { articles: 2024, last_compile_ago: '2h' },
        suggestions: [
          {
            id: 'process-inbox',
            count: 3,
            label: '3 files in inbox/',
            title: '3 new captures to sort',
            verb: 'Sort',
            group: 'do',
            argv: ['process-inbox'],
            priority: 1,
          },
          {
            id: 'compile',
            count: 4,
            label: '4 sources changed since compile',
            title: '4 new sources to add to your wiki',
            verb: 'Add',
            group: 'do',
            argv: ['compile'],
            priority: 2,
          },
          {
            id: 'curiosity-folder',
            count: 2,
            label: '2 document-scan requests to review',
            title: '2 document scans to review',
            verb: 'Review',
            group: 'review',
            argv: ['curiosity', '--type', 'folder-deep-scan'],
            priority: 3,
          },
          {
            id: 'dream-sweep',
            count: 12,
            label: '12 entities overdue for dream',
            title: '12 pages need refreshing',
            verb: 'Refresh',
            group: 'auto',
            argv: ['dream', '--all-entities'],
            priority: 5,
          },
          {
            id: 'lint',
            count: 1,
            label: 'knowledge edits since last lint sweep',
            title: 'Notes changed since the last health check',
            verb: 'Check',
            group: 'auto',
            argv: ['lint', '--structural-only'],
            priority: 7,
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
          {
            id: 'lint',
            title: 'Check for problems',
            verb: 'Check',
            group: 'tools',
            argv: ['lint', '--structural-only'],
          },
          { id: 'links', title: 'Check links', verb: 'Check', group: 'tools', argv: ['links'] },
          {
            id: 'dedup',
            title: 'Find duplicate pages',
            verb: 'Review',
            group: 'tools',
            argv: ['dedup', '--suggest-only'],
          },
          {
            id: 'review-wiki',
            title: 'Review page quality',
            verb: 'Review',
            group: 'tools',
            argv: ['review-wiki'],
          },
        ],
      },
      compileStatus: { running: false, progress: { current: 0, total: 0 } },
      runStatus: { running: null },
    },
    listeners: [
      {
        id: 'screenpipe',
        running: true,
        channels: {
          mic: { lastCaptureAtMs: now - 20_000, ageSeconds: 20, fresh: true },
          system: { lastCaptureAtMs: now - 25_000, ageSeconds: 25, fresh: true },
        },
        zombieSuspected: false,
        checkedAtMs: now,
      },
    ],
    listenerTimeline: timeline(now),
    app: { loginItem: true },
  };
}

const STATES = {
  default: (fx) => fx,
  running: (fx) => {
    fx.vault.compileStatus = { running: true, progress: { current: 3, total: 12 } };
    fx.vault.runStatus = { running: 'compile' };
    return fx;
  },
  'run-progress': (fx) => {
    fx.vault.runStatus = { running: 'process-inbox' };
    return fx;
  },
  'no-access': (fx) => {
    fx.vault.status.accessible = false;
    fx.vault.status.articleCount = 0;
    fx.vault.status.recent = [];
    fx.vault.list = [];
    return fx;
  },
  empty: (fx) => {
    fx.vault.status.articleCount = 0;
    fx.vault.status.lastActivityMs = null;
    fx.vault.status.recent = [];
    fx.vault.list = [];
    fx.vault.triage = [];
    fx.vault.doctor = { issues: 0, updateAvailable: false, checks: [] };
    fx.vault.menu = { status: { articles: 0 }, suggestions: [], tools: [] };
    fx.listeners[0].running = false;
    fx.listeners[0].channels.mic = { lastCaptureAtMs: null, ageSeconds: null, fresh: false };
    fx.listeners[0].channels.system = { lastCaptureAtMs: null, ageSeconds: null, fresh: false };
    fx.listenerTimeline.mic.fill(0);
    fx.listenerTimeline.system.fill(0);
    return fx;
  },
};

/** Build the fixture set for a named state. Unknown names fall back to `default`. */
function build(state, now = Date.now()) {
  const apply = STATES[state] ?? STATES.default;
  return apply(base(now));
}

module.exports = { build, STATES: Object.keys(STATES) };
