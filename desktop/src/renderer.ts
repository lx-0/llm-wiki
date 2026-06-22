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
import { ADVANCED_COMMANDS } from './vault/ipc';

// Live-polling health view + start/stop control. The renderer only calls the
// contextBridge API — no Node, no engine.
const POLL_MS = 5000;
/** in-flight action per listener id, for instant toggle feedback */
const pending = new Map<string, 'start' | 'stop'>();

type Doctor = { issues: number; updateAvailable: boolean; updateMessage?: string };
let doctorState: Doctor | null = null;
/** id of the running engine command (update/advanced), or null. Compile has its own state. */
let advancedBusy: string | null = null;
const advancedResults = new Map<string, boolean>(); // id -> ok

function engineBusy(): boolean {
  return compileState === 'running' || advancedBusy !== null;
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

function fmtAgo(ms: number | null): string {
  if (ms == null) return '—';
  const min = Math.round((Date.now() - ms) / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
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

async function renderVault(): Promise<void> {
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

function renderHealth(): void {
  const el = document.getElementById('health');
  if (!el) return;
  if (!doctorState) {
    el.innerHTML = '';
    return;
  }
  const d = doctorState;
  const health =
    d.issues === 0
      ? `<span class="ok">● Everything healthy</span>`
      : `<span class="warn">⚠ ${d.issues} ${d.issues === 1 ? 'issue' : 'issues'}</span>`;
  el.innerHTML = `<div class="health-row">${health}</div>`;
  if (d.updateAvailable) {
    const row = document.createElement('div');
    row.className = 'update-row';
    row.innerHTML = `<span class="update-msg">App update available</span>`;
    const b = document.createElement('button');
    b.className = 'compile';
    b.textContent = advancedBusy === 'update' ? 'Updating…' : 'Update app';
    b.disabled = engineBusy();
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
    const note = busy ? 'running…' : ok === undefined ? c.hint : ok ? 'done ✓' : 'failed';
    row.innerHTML = `<span class="adv-label">${c.label}<span class="adv-hint">${note}</span></span>`;
    const b = document.createElement('button');
    b.className = 'ghost';
    b.textContent = busy ? '…' : 'Run';
    b.disabled = engineBusy();
    b.addEventListener('click', () => void runEngine(c.id));
    row.appendChild(b);
    el.appendChild(row);
  }
}

async function runEngine(id: string): Promise<void> {
  if (engineBusy()) return;
  advancedBusy = id;
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
    answer.className = 'ask-answer' + (res.ok ? '' : ' err');
    answer.textContent = res.answer || 'No answer.';
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
    const b = document.createElement('button');
    b.className = 'ghost';
    b.textContent = busy ? '…' : 'Run';
    b.disabled = engineBusy();
    b.addEventListener('click', () => void runArgs(s.cmd));
    row.appendChild(b);
    list.appendChild(row);
  }
  el.appendChild(list);
}

async function runArgs(cmd: string): Promise<void> {
  if (engineBusy()) return;
  advancedBusy = cmd;
  renderPending();
  renderHealth();
  renderAdvanced();
  void renderVault();
  const res = await window.vault.runArgs(cmd.split(/\s+/));
  if (!res.started && !res.running) advancedBusy = null;
  renderPending();
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

  // Footer: autostart toggle + quit.
  const loginToggle = document.getElementById('login-toggle') as HTMLInputElement | null;
  void window.app.getLoginItem().then((on) => {
    if (loginToggle) loginToggle.checked = on;
  });
  loginToggle?.addEventListener('change', () => {
    const want = loginToggle.checked;
    void window.app
      .setLoginItem(want)
      .then((actual) => {
        loginToggle.checked = actual; // reflect the real registered state
        loginToggle.title =
          actual === want
            ? ''
            : 'Login items register only for the installed app (drag to Applications) — not in dev mode';
        if (actual !== want) console.warn('login item did not persist (dev mode or app not in /Applications?)');
      })
      .catch((e) => console.error('setLoginItem failed', e));
  });
  document.getElementById('quit')?.addEventListener('click', () => window.app.quit());

  // Ask: button + Enter key.
  document.getElementById('ask-btn')?.addEventListener('click', () => void ask());
  document.getElementById('ask-input')?.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter') void ask();
  });

  renderAdvanced();

  // Auto-fit the window to content — no scrolling. Fires on any layout change
  // (health/update appearing, advanced expanding, status changes).
  const fit = () => window.panel.resize(document.documentElement.scrollHeight);
  new ResizeObserver(fit).observe(document.body);
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

  // Advanced / update / suggestion command finished (pushed from main).
  window.vault.onRunDone(({ id, result }) => {
    if (advancedBusy === id) advancedBusy = null;
    advancedResults.set(id, result.ok);
    renderAdvanced();
    renderPending();
    void renderVault(); // re-enable buttons
    void loadDoctor(); // refresh health + update-available (esp. after `update`)
    void loadMenu(); // the pending list shrinks as work gets done
    if (id === 'update' || id === 'dedup') void renderStatus();
  });

  window.addEventListener('beforeunload', () => {
    window.clearInterval(t1);
    window.clearInterval(t2);
  });
});
