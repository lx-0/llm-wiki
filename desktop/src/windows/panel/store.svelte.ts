// Panel state — the one source every panel section reads from. Loaders talk to the preload
// bridge; events from the main process (compile / run progress + done, visibility) land here;
// components only render what is in `panel` and call the actions below.

type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
type Entry = Awaited<ReturnType<typeof window.vault.list>>[number];
type Doctor = Awaited<ReturnType<typeof window.vault.doctor>>;
type Menu = Awaited<ReturnType<typeof window.vault.menu>>;
type Listener = Awaited<ReturnType<typeof window.listeners.status>>[number];
type Progress = { current: number; total: number };

export const panel = $state({
  visible: false,
  loaded: false,
  vault: null as VaultStatus,
  entries: [] as Entry[],
  doctor: null as Doctor,
  menu: null as Menu,
  listeners: [] as Listener[],
  /** pending inbox records (header badge) */
  inbox: 0,
  compile: {
    running: false,
    progress: { current: 0, total: 0 } as Progress,
    /** last outcome, kept until the panel closes */
    result: null as { ok: boolean; durationMs: number } | null,
  },
  run: {
    /** argv key of the engine command in flight (anything but compile), or null */
    key: null as string | null,
    progress: null as Progress | null,
    /** argv key → ok, kept until the panel closes */
    results: new Map<string, boolean>(),
  },
  /** in-flight listener toggles, for instant feedback */
  toggling: new Map<string, 'start' | 'stop'>(),
});

const LISTENER_POLL_MS = 5000;

export function busy(): boolean {
  return panel.compile.running || panel.run.key !== null;
}

export async function refresh(): Promise<void> {
  const [vault, entries, doctor, menu, listeners, inbox, compileStatus, runStatus] = await Promise.all([
    window.vault.status().catch(() => null),
    window.vault.list().catch(() => [] as Entry[]),
    window.vault.doctor().catch(() => null),
    window.vault.menu().catch(() => null),
    window.listeners.status().catch(() => [] as Listener[]),
    window.vault
      .triage(false)
      .then((records) => records.length)
      .catch(() => 0),
    window.vault.compileStatus().catch(() => ({ running: false, progress: { current: 0, total: 0 } })),
    window.vault.runStatus().catch(() => ({ running: null })),
  ]);
  panel.vault = vault;
  panel.entries = entries;
  panel.doctor = doctor;
  panel.menu = menu;
  panel.listeners = listeners;
  panel.inbox = inbox;
  panel.compile.running = compileStatus.running;
  if (compileStatus.running) panel.compile.progress = compileStatus.progress;
  panel.run.key = runStatus.running && runStatus.running !== 'compile' ? runStatus.running : null;
  panel.loaded = true;
}

export async function refreshListeners(): Promise<void> {
  panel.listeners = await window.listeners.status().catch(() => panel.listeners);
}

/** Wire the main-process events once (call from the root component's mount). */
export function connect(): () => void {
  window.panel.onVisibility((visible) => {
    panel.visible = visible;
    if (visible) {
      void refresh();
    } else {
      // the highlighted results have been seen
      panel.run.results = new Map();
      panel.compile.result = null;
    }
  });
  window.vault.onCompileProgress((progress) => {
    panel.compile.progress = progress;
  });
  window.vault.onCompileDone((result) => {
    panel.compile.running = false;
    panel.compile.result = result;
    void refresh();
  });
  window.vault.onRunProgress(({ id, progress }) => {
    if (panel.run.key === id) panel.run.progress = progress;
  });
  window.vault.onRunDone(({ id, result }) => {
    if (panel.run.key === id) panel.run.key = null;
    panel.run.progress = null;
    panel.run.results.set(id, result.ok);
    panel.run.results = new Map(panel.run.results);
    void refresh();
  });
  const timer = window.setInterval(() => {
    if (panel.visible && panel.toggling.size === 0) void refreshListeners();
  }, LISTENER_POLL_MS);
  return () => window.clearInterval(timer);
}

export async function runAction(argv: string[]): Promise<void> {
  if (busy() || argv.length === 0) return;
  const key = argv.join(' ');
  panel.run.key = key;
  panel.run.progress = null;
  panel.run.results.delete(key);
  panel.run.results = new Map(panel.run.results);
  const res = await window.vault.runArgs(argv);
  if (!res.started && !res.running) panel.run.key = null;
}

export async function startCompile(): Promise<void> {
  if (busy()) return;
  const res = await window.vault.compile();
  if (res.started || res.running) {
    panel.compile.running = true;
    panel.compile.result = null;
    panel.compile.progress = { current: 0, total: 0 };
  }
}

export async function toggleListener(id: string, action: 'start' | 'stop'): Promise<void> {
  if (panel.toggling.has(id)) return;
  panel.toggling.set(id, action);
  panel.toggling = new Map(panel.toggling);
  try {
    await window.listeners.control(id, action);
    await new Promise((resolve) => setTimeout(resolve, 1500)); // let launchd flip state
  } finally {
    panel.toggling.delete(id);
    panel.toggling = new Map(panel.toggling);
    await refreshListeners();
  }
}

export async function ask(question: string): Promise<{ ok: boolean; answer: string }> {
  const res = await window.vault.query(question);
  return { ok: res.ok, answer: res.answer || (res.ok ? '' : 'No answer.') };
}
