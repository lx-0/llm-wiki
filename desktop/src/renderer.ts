/**
 * This file will automatically be loaded by vite and run in the "renderer" context.
 * To learn more about the differences between the "main" and the "renderer" context in
 * Electron, visit:
 *
 * https://electronjs.org/docs/tutorial/process-model
 *
 * By default, Node.js integration in this file is disabled. When enabling Node.js integration
 * in a renderer process, please be aware of potential security implications. You can read
 * more about security risks here:
 *
 * https://electronjs.org/docs/tutorial/security
 *
 * To enable Node.js integration in this file, open up `main.ts` and enable the `nodeIntegration`
 * flag:
 *
 * ```
 *  // Create the browser window.
 *  mainWindow = new BrowserWindow({
 *    width: 800,
 *    height: 600,
 *    webPreferences: {
 *      nodeIntegration: true
 *    }
 *  });
 * ```
 */

import './index.css';
import { marked } from 'marked';
import { ADVANCED_COMMANDS } from './vault/ipc';
import { fmtAgo } from './lib/time';

const ICON_COPY = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const ICON_CHECK = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`;
const ICON_X = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

/** Hide + empty the Ask answer (the × button). The popover re-fits via the observer. */
function clearAnswer(): void {
  const answer = document.getElementById('ask-answer');
  if (!answer) return;
  answer.hidden = true;
  answer.innerHTML = '';
  answer.className = 'ask-answer';
}

/** Render the answer markdown to HTML; wikilinks [[a/b/slug]] / [[path|alias]] →
 *  a clickable chip that opens the file in Obsidian (data-file carries the ref). */
function renderMarkdown(md: string): string {
  const withLinks = md.replace(/\[\[([^\]]+)\]\]/g, (_m, inner: string) => {
    const ref = inner.split('|')[0].split('#')[0].trim();
    const name = (inner.includes('|') ? inner.split('|')[1] : ref.split('/').pop() || ref).trim();
    return `<span class="wl" data-file="${escapeHtml(ref)}">${escapeHtml(name)}</span>`;
  });
  return marked.parse(withLinks, { breaks: true, async: false }) as string;
}

// Live-polling health view + start/stop control. The renderer only calls the
// contextBridge API — no Node, no engine.
const POLL_MS = 5000;
/** in-flight action per listener id, for instant toggle feedback */
const pending = new Map<string, 'start' | 'stop'>();

type DoctorCheck = { id: string; severity: string; message: string; fix?: string; dispatchArgs?: string[] };
type Doctor = { issues: number; updateAvailable: boolean; updateMessage?: string; checks?: DoctorCheck[] };
let doctorState: Doctor | null = null;
let healthExpanded = false;
/** id of the running engine command (update/advanced), or null. Compile has its own state. */
let advancedBusy: string | null = null;
/** [i/total] progress of the running advanced/suggestion command (if it emits any). */
let runProgress: { current: number; total: number } | null = null;
const advancedResults = new Map<string, boolean>(); // id -> ok

/** "Add to wiki" link-ingest state (runs through the same engine runner). */
let addingId: string | null = null;
let addState: 'idle' | 'adding' | 'done' | 'failed' | 'invalid' = 'idle';

function engineBusy(): boolean {
  return compileState === 'running' || advancedBusy !== null;
}

/** A spinner, plus "x of y" when the running command reports progress. */
function runningIndicator(): HTMLElement {
  const el = document.createElement('span');
  el.className = 'run-prog';
  const xy = runProgress && runProgress.total > 0 ? `${runProgress.current} of ${runProgress.total}` : '';
  el.innerHTML = `<span class="spin" aria-hidden="true"></span>${xy ? `<span class="run-x">${xy}</span>` : ''}`;
  return el;
}

function fmtClock(ms: number | null): string {
  return ms == null ? '—' : new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtDur(sec: number | null): string {
  if (sec == null) return '—';
  return sec < 90 ? `${sec}s` : `${Math.round(sec / 60)}m`;
}

type Status = Awaited<ReturnType<typeof window.listeners.status>>[number];

/** One clear, human line — semantic state, not a raw growing counter. */
function summaryLine(s: Status): string {
  const p = pending.get(s.id);
  if (p) return p === 'start' ? 'starting…' : 'stopping…';
  if (!s.running) return `stopped · last capture ${fmtClock(s.channels.mic.lastCaptureAtMs)}`;
  const mic = s.channels.mic, sys = s.channels.system;
  if (mic.fresh && sys.fresh) return 'capturing · mic + system audio';
  const parts: string[] = [];
  parts.push(mic.fresh ? 'mic ✓' : `mic silent ${fmtDur(mic.ageSeconds)}`);
  parts.push(sys.fresh ? 'system ✓' : `system silent ${fmtDur(sys.ageSeconds)}`);
  return parts.join(' · ');
}

async function renderStatus(): Promise<void> {
  const el = document.getElementById('listeners');
  if (!el) return;
  try {
    const statuses = await window.listeners.status();
    el.innerHTML = '';
    for (const s of statuses) {
      const p = pending.get(s.id);
      const state = p ? 'busy' : !s.running ? 'stopped' : s.zombieSuspected ? 'zombie' : 'running';
      const card = document.createElement('li');
      card.className = 'listener';
      card.innerHTML = `
        <div class="head">
          <span class="dot ${state}"></span>
          <span class="name">${s.id}</span>
        </div>
        <div class="summary ${state}">${summaryLine(s)}</div>`;
      const btn = document.createElement('button');
      btn.className = s.running ? 'stop' : 'start';
      btn.textContent = p ? '…' : s.running ? 'Stop' : 'Start';
      btn.disabled = Boolean(p);
      btn.addEventListener('click', () => void control(s.id, s.running ? 'stop' : 'start'));
      card.querySelector('.head')?.appendChild(btn);
      el.appendChild(card);
    }
  } catch (err) {
    el.textContent = `status error: ${String(err)}`;
    console.error(err);
  }
}

async function control(id: string, action: 'start' | 'stop'): Promise<void> {
  if (pending.has(id)) return;
  pending.set(id, action); // instant feedback (starting…/stopping…)
  void renderStatus();
  try {
    const res = await window.listeners.control(id, action);
    if (!res.ok) console.error(`${action} ${id} failed:`, res.error);
    // give the daemon a moment to actually flip launchd state before we re-read
    await new Promise((r) => setTimeout(r, 1500));
  } finally {
    pending.delete(id);
    void renderStatus();
  }
}


type CompileState = 'idle' | 'running' | { ok: boolean; durationMs: number };
let compileState: CompileState = 'idle';
let compileProgress = { current: 0, total: 0 };

function compileLine(): string {
  if (compileState === 'running') {
    const { current, total } = compileProgress;
    if (total > 0) return `Updating knowledge · ${current} of ${total}`;
    return 'Updating knowledge…';
  }
  if (compileState !== 'idle') {
    const m = Math.max(1, Math.round(compileState.durationMs / 60000));
    return compileState.ok ? `Up to date · took ${m}m` : 'Update failed — try again';
  }
  return '';
}

function progressBar(): string {
  if (compileState !== 'running') return '';
  const { current, total } = compileProgress;
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  const indeterminate = total === 0;
  return `<div class="bar ${indeterminate ? 'indeterminate' : ''}"><div class="fill" style="width:${pct}%"></div></div>`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

// "New since you last looked": entries with mtime > recentSeenMs are highlighted;
// recentSeenMs advances when the panel closes (so they're no longer new next time).
// Defaults to now on first run, so nothing is flagged until something actually changes.
let recentSeenMs = ((): number => {
  const stored = localStorage.getItem('recentSeenMs');
  if (stored) return Number(stored);
  const now = Date.now();
  localStorage.setItem('recentSeenMs', String(now));
  return now;
})();
let lastRecentNewest = 0;

/** Most recently modified knowledge entries; click opens the file in Obsidian. */
function renderRecent(recent: { title: string; file: string; type: string; mtimeMs: number }[]): void {
  const el = document.getElementById('recent');
  if (!el) return;
  if (!recent || recent.length === 0) {
    el.innerHTML = '';
    return;
  }
  el.innerHTML = `<h2 class="section-label">Recent entries</h2>`;
  const list = document.createElement('div');
  list.className = 'recent-list card';
  let newest = 0;
  for (const r of recent) {
    newest = Math.max(newest, r.mtimeMs);
    const row = document.createElement('button');
    row.className = r.mtimeMs > recentSeenMs ? 'recent-row new' : 'recent-row';
    row.title = 'Open in Obsidian';
    const cls = r.type.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() || 'note';
    row.innerHTML =
      `<span class="type-badge t-${cls}">${escapeHtml(r.type)}</span>` +
      `<span class="recent-title">${escapeHtml(r.title)}</span>` +
      `<span class="recent-ago">${fmtAgo(r.mtimeMs)}</span>`;
    row.addEventListener('click', () => window.vault.openFile(r.file));
    list.appendChild(row);
  }
  lastRecentNewest = newest;
  el.appendChild(list);
}

async function renderVault(): Promise<void> {
  syncAddBtn(); // keep the "Add" button's enabled state in sync with engine busy
  const meta = document.getElementById('vault-meta');
  const box = document.getElementById('vault');
  try {
    const v = await window.vault.status();
    if (!v) {
      if (meta) meta.textContent = 'no vault';
      if (box) box.textContent = '';
      return;
    }
    if (meta) {
      meta.innerHTML = `${v.name} <span class="ext">↗</span>`;
      meta.title = 'Open in Obsidian';
      meta.classList.add('link');
    }
    renderRecent(v.recent ?? []);
    if (box) {
      if (!v.accessible) {
        // Can't read the vault — almost always macOS file access (the vault is
        // under iCloud Drive; a Finder-launched app needs Full Disk Access).
        box.innerHTML = `
          <div class="vault-warn">⚠ Can't read your vault</div>
          <div class="vault-path">${v.path.replace(/^\/Users\/[^/]+/, '~')}</div>
          <div class="vault-hint">Grant <b>Full Disk Access</b> to llm-wiki in System Settings → Privacy &amp; Security, then reopen.</div>`;
        const fix = document.createElement('button');
        fix.className = 'compile';
        fix.textContent = 'Open Settings';
        fix.addEventListener('click', () => void window.vault.openFullDiskAccess());
        box.appendChild(fix);
        return;
      }
      const running = compileState === 'running';
      box.innerHTML = `
        <div class="vault-row"><span class="big">${v.articleCount.toLocaleString()}</span><span class="muted">notes · updated ${fmtAgo(v.lastActivityMs)}</span></div>
        <div class="vault-path" title="${v.path}">${v.path.replace(/^\/Users\/[^/]+/, '~')}</div>
        ${progressBar()}
        <div class="vault-actions">
          <span class="compile-state ${running ? 'running' : ''}">${compileLine()}</span>
        </div>`;
      const btn = document.createElement('button');
      btn.className = 'compile';
      btn.title = 'Turn newly captured material (notes, voice, screenshots, meetings) into wiki articles';
      btn.textContent = running ? 'Updating…' : 'Update knowledge';
      btn.disabled = engineBusy();
      btn.addEventListener('click', () => void compile());
      box.querySelector('.vault-actions')?.appendChild(btn);
    }
  } catch (err) {
    console.error(err);
  }
}

// --- Health + update -------------------------------------------------------
async function loadDoctor(): Promise<void> {
  doctorState = await window.vault.doctor();
  renderHealth();
}

async function fixCheck(args: string[]): Promise<void> {
  if (engineBusy() || args.length === 0) return;
  advancedBusy = args.join(' ');
  runProgress = null;
  renderHealth();
  renderAdvanced();
  renderPending();
  void renderVault();
  const res = await window.vault.runArgs(args);
  if (!res.started && !res.running) advancedBusy = null;
  renderHealth();
}

function renderHealth(): void {
  const el = document.getElementById('health');
  if (!el) return;
  if (!doctorState) {
    el.innerHTML = '';
    return;
  }
  const d = doctorState;
  el.innerHTML = '';

  const row = document.createElement('div');
  row.className = 'health-row';
  if (d.issues === 0) {
    row.innerHTML = `<span class="ok">● Everything healthy</span>`;
  } else {
    row.innerHTML = `<span class="warn">⚠ ${d.issues} ${d.issues === 1 ? 'issue' : 'issues'}</span><span class="chev">${healthExpanded ? '▾' : '▸'}</span>`;
    row.classList.add('clickable');
    row.addEventListener('click', () => {
      healthExpanded = !healthExpanded;
      renderHealth();
    });
  }
  el.appendChild(row);

  // Expanded: the individual checks, each with a Fix button when runnable.
  if (d.issues > 0 && healthExpanded) {
    const list = document.createElement('div');
    list.className = 'health-list card';
    for (const c of d.checks ?? []) {
      const r = document.createElement('div');
      r.className = 'health-item';
      const runnable = c.dispatchArgs && c.dispatchArgs.length > 0 && !/auth/.test(c.dispatchArgs.join(' '));
      const busy = advancedBusy === (c.dispatchArgs?.join(' ') ?? '');
      r.innerHTML = `<span class="sev sev-${c.severity}"></span><span class="health-msg">${escapeHtml(c.message)}</span>`;
      if (busy) {
        r.appendChild(runningIndicator());
      } else if (runnable) {
        const b = document.createElement('button');
        b.className = 'ghost';
        b.textContent = 'Fix';
        b.disabled = engineBusy();
        b.addEventListener('click', () => void fixCheck(c.dispatchArgs as string[]));
        r.appendChild(b);
      } else if (c.fix) {
        const hint = document.createElement('code');
        hint.className = 'health-fix';
        hint.textContent = c.fix;
        r.appendChild(hint);
      }
      list.appendChild(r);
    }
    el.appendChild(list);
  }

  if (d.updateAvailable) {
    const row = document.createElement('div');
    row.className = 'update-row';
    row.innerHTML = `<span class="update-msg">App update available</span>`;
    const b = document.createElement('button');
    b.className = 'compile';
    if (advancedBusy === 'update') {
      b.innerHTML = `<span class="spin light" aria-hidden="true"></span> Updating…`;
      b.disabled = true;
    } else {
      b.textContent = 'Update app';
      b.disabled = engineBusy();
    }
    b.addEventListener('click', () => void runEngine('update'));
    row.appendChild(b);
    el.appendChild(row);
  }
}

// --- Advanced ---------------------------------------------------------------
function renderAdvanced(): void {
  const el = document.getElementById('advanced-actions');
  if (!el) return;
  el.innerHTML = '';
  for (const c of ADVANCED_COMMANDS) {
    const row = document.createElement('div');
    row.className = 'adv-row';
    const busy = advancedBusy === c.id;
    const ok = advancedResults.get(c.id);
    const note = busy ? '' : ok === undefined ? c.hint : ok ? 'done ✓' : 'failed';
    row.innerHTML = `<span class="adv-label">${c.label}<span class="adv-hint">${note}</span></span>`;
    if (busy) {
      row.appendChild(runningIndicator());
    } else {
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = 'Run';
      b.disabled = engineBusy();
      b.addEventListener('click', () => void runEngine(c.id));
      row.appendChild(b);
    }
    el.appendChild(row);
  }
}

async function runEngine(id: string): Promise<void> {
  if (engineBusy()) return;
  advancedBusy = id;
  runProgress = null;
  renderHealth();
  renderAdvanced();
  void renderVault(); // reflect disabled compile button
  const res = await window.vault.run(id as never);
  if (!res.started && !res.running) advancedBusy = null;
  renderHealth();
  renderAdvanced();
}

// --- Ask (query) -----------------------------------------------------------
let asking = false;
async function ask(): Promise<void> {
  const input = document.getElementById('ask-input') as HTMLInputElement | null;
  const answer = document.getElementById('ask-answer');
  const btn = document.getElementById('ask-btn') as HTMLButtonElement | null;
  if (!input || !answer || asking) return;
  const q = input.value.trim();
  if (!q) return;
  asking = true;
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  answer.hidden = false;
  answer.className = 'ask-answer thinking';
  answer.textContent = 'Thinking…';
  try {
    const res = await window.vault.query(q);
    if (res.ok) {
      answer.className = 'ask-answer';
      answer.innerHTML =
        `<div class="ask-tools">` +
        `<button class="icon-btn copy" title="Copy to clipboard">${ICON_COPY}</button>` +
        `<button class="icon-btn clear" title="Clear">${ICON_X}</button>` +
        `</div><div class="md">${renderMarkdown(res.answer)}</div>`;
      const copyBtn = answer.querySelector('.copy') as HTMLButtonElement | null;
      copyBtn?.addEventListener('click', () => {
        void navigator.clipboard.writeText(res.answer).then(() => {
          copyBtn.innerHTML = ICON_CHECK;
          copyBtn.classList.add('done');
          window.setTimeout(() => {
            copyBtn.innerHTML = ICON_COPY;
            copyBtn.classList.remove('done');
          }, 1500);
        });
      });
      answer.querySelector('.clear')?.addEventListener('click', clearAnswer);
    } else {
      answer.className = 'ask-answer err';
      answer.innerHTML = `<div class="ask-tools"><button class="icon-btn clear" title="Clear">${ICON_X}</button></div><div class="md-plain"></div>`;
      const plain = answer.querySelector('.md-plain');
      if (plain) plain.textContent = res.answer || 'No answer.';
      answer.querySelector('.clear')?.addEventListener('click', clearAnswer);
    }
  } catch {
    answer.className = 'ask-answer err';
    answer.textContent = 'Something went wrong.';
  } finally {
    asking = false;
    if (btn) { btn.disabled = false; btn.textContent = 'Ask'; }
  }
}

// --- What's pending (the engine's own actionable menu) ---------------------
type Menu = {
  status: { articles?: number; last_compile_ago?: string };
  suggestions: { count: number; label: string; cmd: string; priority: number; group: string }[];
};
let menuState: Menu | null = null;

async function loadMenu(): Promise<void> {
  menuState = (await window.vault.menu()) as Menu | null;
  renderPending();
}

function renderPending(): void {
  const el = document.getElementById('pending');
  if (!el) return;
  const items = (menuState?.suggestions ?? []).slice(0, 5);
  if (items.length === 0) {
    el.innerHTML = '';
    return;
  }
  el.innerHTML = `<h2 class="section-label">What's pending</h2>`;
  const list = document.createElement('div');
  list.className = 'pending-list card';
  for (const s of items) {
    const row = document.createElement('div');
    row.className = 'pending-row';
    const busy = advancedBusy === s.cmd;
    row.innerHTML = `<span class="pending-label">${s.label}</span>`;
    if (busy) {
      row.appendChild(runningIndicator());
    } else {
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = 'Run';
      b.disabled = engineBusy();
      b.addEventListener('click', () => void runArgs(s.cmd));
      row.appendChild(b);
    }
    list.appendChild(row);
  }
  el.appendChild(list);
}

async function runArgs(cmd: string): Promise<void> {
  if (engineBusy()) return;
  advancedBusy = cmd;
  runProgress = null;
  renderPending();
  renderHealth();
  renderAdvanced();
  void renderVault();
  const res = await window.vault.runArgs(cmd.split(/\s+/));
  if (!res.started && !res.running) advancedBusy = null;
  renderPending();
}

// --- Sync sources (collectors) ---
let collectorsLoaded = false;
let collectorList: { name: string; configured: boolean }[] = [];
const syncQueue: string[] = [];

async function loadCollectors(): Promise<void> {
  if (collectorsLoaded) return;
  collectorsLoaded = true;
  collectorList = await window.vault.collectors();
  renderSources();
}

function renderSources(): void {
  const el = document.getElementById('sources-list');
  if (!el) return;
  if (collectorList.length === 0) {
    el.innerHTML = `<div class="adv-row"><span class="adv-label">No sources found<span class="adv-hint">configure collectors first</span></span></div>`;
    return;
  }
  const configured = collectorList.filter((c) => c.configured);
  el.innerHTML = '';
  if (configured.length > 1) {
    const row = document.createElement('div');
    row.className = 'adv-row';
    row.innerHTML = `<span class="adv-label">Sync all<span class="adv-hint">${configured.length} configured</span></span>`;
    const b = document.createElement('button');
    b.className = 'ghost';
    b.textContent = syncQueue.length ? '…' : 'Sync all';
    b.disabled = engineBusy();
    b.addEventListener('click', () => syncAll());
    row.appendChild(b);
    el.appendChild(row);
  }
  for (const c of configured) {
    const id = `collect ${c.name} --incremental`;
    const row = document.createElement('div');
    row.className = 'adv-row';
    row.innerHTML = `<span class="adv-label">${escapeHtml(c.name)}</span>`;
    if (advancedBusy === id) {
      row.appendChild(runningIndicator());
    } else {
      const b = document.createElement('button');
      b.className = 'ghost';
      b.textContent = 'Sync';
      b.disabled = engineBusy();
      b.addEventListener('click', () => void runArgs(id));
      row.appendChild(b);
    }
    el.appendChild(row);
  }
}

function syncAll(): void {
  if (engineBusy()) return;
  const names = collectorList.filter((c) => c.configured).map((c) => c.name);
  if (!names.length) return;
  syncQueue.length = 0;
  syncQueue.push(...names);
  void runArgs(`collect ${syncQueue.shift()} --incremental`);
}

// Pending-triage count on the header inbox button.
async function renderTriageBadge(): Promise<void> {
  const badge = document.getElementById('triage-badge');
  if (!badge) return;
  const n = (await window.vault.triage(false)).length;
  badge.textContent = n ? String(n) : '';
  badge.hidden = n === 0;
}

// --- Add to wiki (ingest a link) -------------------------------------------
function syncAddBtn(): void {
  const b = document.getElementById('add-btn') as HTMLButtonElement | null;
  if (b) b.disabled = engineBusy();
}

function renderAddStatus(): void {
  const el = document.getElementById('add-status');
  if (!el) return;
  if (addState === 'idle') {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  el.hidden = false;
  if (addState === 'adding') {
    const xy = runProgress && runProgress.total > 0 ? ` · ${runProgress.current} of ${runProgress.total}` : '';
    el.className = 'add-status';
    el.innerHTML = `<span class="spin" aria-hidden="true"></span><span>Adding…${xy}</span>`;
  } else if (addState === 'done') {
    el.className = 'add-status ok';
    el.textContent = 'Added ✓ — it appears after the next Update.';
  } else if (addState === 'failed') {
    el.className = 'add-status err';
    el.textContent = "Couldn't add that link.";
  } else {
    el.className = 'add-status err';
    el.textContent = 'Paste a web page or YouTube link.';
  }
}

async function addToWiki(): Promise<void> {
  const input = document.getElementById('add-input') as HTMLInputElement | null;
  if (!input) return;
  const url = input.value.trim();
  if (!url) return;
  if (engineBusy()) {
    addState = 'adding'; // something else is running; the runner will reject — nudge to wait
    renderAddStatus();
    return;
  }
  let args: string[] | null = null;
  if (/(?:youtube\.com|youtu\.be)\//i.test(url)) args = ['ingest-youtube', '--url', url];
  else if (/^https?:\/\//i.test(url)) args = ['ingest-html', url];
  if (!args) {
    addState = 'invalid';
    renderAddStatus();
    return;
  }
  addingId = args.join(' ');
  advancedBusy = addingId;
  runProgress = null;
  addState = 'adding';
  input.value = '';
  renderAddStatus();
  renderPending();
  renderAdvanced();
  renderHealth();
  void renderVault();
  const res = await window.vault.runArgs(args);
  if (!res.started && !res.running) {
    addingId = null;
    advancedBusy = null;
    addState = 'failed';
    renderAddStatus();
  }
}

async function compile(): Promise<void> {
  if (engineBusy()) return;
  const res = await window.vault.compile();
  if (res.started || res.running) {
    compileState = 'running';
    void renderVault();
  } else if (res.error) {
    console.error('compile:', res.error);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  // Visibility is driven by MAIN (authoritative). Starts hidden ⇒ no polling
  // until the panel is opened — a closed menubar panel does zero work.
  let panelVisible = false;

  const t1 = window.setInterval(() => {
    if (panelVisible && pending.size === 0) void renderStatus();
  }, POLL_MS);
  const t2 = window.setInterval(() => {
    if (panelVisible) void renderVault();
  }, 60_000);

  // Vault-name pill opens the vault in Obsidian (reading surface).
  document.getElementById('vault-meta')?.addEventListener('click', () => {
    void window.vault.openInObsidian();
  });

  // Header: cockpit (expand) → Cockpit window; browse (magnifier) → Browse; gear → Settings.
  document.getElementById('cockpit-btn')?.addEventListener('click', () => window.app.openCockpit());
  document.getElementById('atlas-btn')?.addEventListener('click', () => window.app.openAtlas());
  document.getElementById('browse-btn')?.addEventListener('click', () => window.app.openBrowse());
  document.getElementById('triage-btn')?.addEventListener('click', () => window.app.openTriage());
  document.getElementById('settings-btn')?.addEventListener('click', () => window.app.openSettings());
  document.getElementById('quit')?.addEventListener('click', () => window.app.quit());

  // Ask: button + Enter key.
  document.getElementById('ask-btn')?.addEventListener('click', () => void ask());
  document.getElementById('ask-input')?.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter') void ask();
  });
  // Clickable wikilinks in the answer → open in Obsidian (delegated; survives re-render).
  document.getElementById('ask-answer')?.addEventListener('click', (e) => {
    const t = (e.target as HTMLElement).closest('.wl') as HTMLElement | null;
    if (t?.dataset.file) window.vault.openFile(t.dataset.file);
  });

  // Add to wiki: button + Enter.
  document.getElementById('add-btn')?.addEventListener('click', () => void addToWiki());
  document.getElementById('add-input')?.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter') void addToWiki();
  });

  renderAdvanced();
  void renderTriageBadge();

  // Auto-fit the window to content — no scrolling. Fires on any layout change
  // (health/update appearing, advanced expanding, status changes).
  const fit = () => window.panel.resize(document.documentElement.scrollHeight);
  new ResizeObserver(fit).observe(document.body);
  // Explicit fit on every disclosure expand/collapse (belt-and-suspenders vs the observer).
  document.querySelectorAll('details').forEach((d) => d.addEventListener('toggle', fit));
  document.getElementById('sources')?.addEventListener('toggle', (e) => {
    if ((e.target as HTMLDetailsElement).open) void loadCollectors(); // lazy — spawns the CLI
  });
  fit();

  window.panel.onVisibility((v) => {
    panelVisible = v;
    if (v) {
      // fresh on open + restore running state (compile or advanced)
      void window.vault.compileStatus().then((s) => {
        if (s.running) {
          compileState = 'running';
          compileProgress = s.progress;
        }
        void renderVault();
      });
      void window.vault.runStatus().then((s) => {
        advancedBusy = s.running && s.running !== 'compile' ? s.running : null;
        renderAdvanced();
        renderHealth();
      });
      void renderStatus();
      void renderVault();
      void loadDoctor(); // health + update-available (read-only, ~seconds)
      void loadMenu(); // what's pending (engine's actionable suggestions)
      void renderTriageBadge(); // inbox count on the triage button
      window.setTimeout(() => document.getElementById('ask-input')?.focus(), 30); // search-first
    } else if (lastRecentNewest > recentSeenMs) {
      // panel closed → the highlighted-new entries are now "seen"
      recentSeenMs = lastRecentNewest;
      localStorage.setItem('recentSeenMs', String(recentSeenMs));
    }
  });

  window.vault.onCompileProgress((p) => {
    compileProgress = p;
    if (compileState === 'running') void renderVault();
  });

  // Compile finished (pushed from main): show result, refresh stats + health, reset later.
  window.vault.onCompileDone((r) => {
    compileState = { ok: r.ok, durationMs: r.durationMs };
    void renderVault();
    void loadDoctor();
    window.setTimeout(() => {
      compileState = 'idle';
      void renderVault();
    }, 8000);
  });

  // Per-step progress for the running advanced/suggestion command (if it emits [i/total]).
  window.vault.onRunProgress(({ id, progress }) => {
    if (advancedBusy !== id) return;
    runProgress = progress;
    renderPending();
    renderAdvanced();
    renderHealth();
    renderSources();
    if (addingId === id) renderAddStatus();
  });

  // Advanced / update / suggestion command finished (pushed from main).
  window.vault.onRunDone(({ id, result }) => {
    if (advancedBusy === id) advancedBusy = null;
    runProgress = null;
    advancedResults.set(id, result.ok);
    renderAdvanced();
    renderPending();
    void renderVault(); // re-enable buttons
    void loadDoctor(); // refresh health + update-available (esp. after `update`)
    void loadMenu(); // the pending list shrinks as work gets done
    if (id === 'update' || id === 'dedup') void renderStatus();
    renderSources();
    // sync-all: when one collector finishes, kick off the next queued one
    if (syncQueue.length) void runArgs(`collect ${syncQueue.shift()} --incremental`);
    if (id === addingId) {
      addingId = null;
      addState = result.ok ? 'done' : 'failed';
      renderAddStatus();
      window.setTimeout(() => {
        addState = 'idle';
        renderAddStatus();
      }, 6000);
    }
  });

  window.addEventListener('beforeunload', () => {
    window.clearInterval(t1);
    window.clearInterval(t2);
  });
});
