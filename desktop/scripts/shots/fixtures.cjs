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
  return out.sort((a, b) => b.mtimeMs - a.mtimeMs);
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
            id: 'dream-overdue',
            severity: 'warning',
            message: '12 entity pages overdue for dream',
            fix: 'wiki dream --all-entities',
            dispatchArgs: ['dream', '--all-entities'],
          },
          {
            id: 'links',
            severity: 'critical',
            message: '7 broken wikilinks in knowledge/',
            fix: 'wiki links --fix',
            dispatchArgs: ['links', '--fix', '--yes'],
          },
          {
            id: 'ollama',
            severity: 'warning',
            message: 'Ollama unreachable at 192.168.2.42:11434',
            fix: 'check kcma-d8 is up',
          },
        ],
      },
      query: { ok: true, answer: ANSWER },
      menu: {
        status: { articles: 2024, last_compile_ago: '2h' },
        suggestions: [
          { count: 3, label: '3 files in inbox/', cmd: 'process-inbox', priority: 1, group: 'do' },
          { count: 4, label: '4 sources changed since compile', cmd: 'compile', priority: 2, group: 'do' },
          {
            count: 2,
            label: '2 document-scan requests to review',
            cmd: 'curiosity --type folder-deep-scan',
            priority: 3,
            group: 'review',
          },
          {
            count: 12,
            label: '12 entities overdue for dream',
            cmd: 'dream --all-entities',
            priority: 5,
            group: 'auto',
          },
          {
            count: 1,
            label: 'knowledge edits since last lint sweep',
            cmd: 'lint --structural-only',
            priority: 7,
            group: 'auto',
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
    fx.vault.menu = { status: { articles: 0 }, suggestions: [] };
    fx.listeners[0].running = false;
    fx.listeners[0].channels.mic = { lastCaptureAtMs: null, ageSeconds: null, fresh: false };
    fx.listeners[0].channels.system = { lastCaptureAtMs: null, ageSeconds: null, fresh: false };
    return fx;
  },
};

/** Build the fixture set for a named state. Unknown names fall back to `default`. */
function build(state, now = Date.now()) {
  const apply = STATES[state] ?? STATES.default;
  return apply(base(now));
}

module.exports = { build, STATES: Object.keys(STATES) };
