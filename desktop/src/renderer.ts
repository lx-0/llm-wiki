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

// Live-polling health view + start/stop control. The renderer only calls the
// contextBridge API — no Node, no engine.
const POLL_MS = 3000;
/** in-flight action per listener id, for instant toggle feedback */
const pending = new Map<string, 'start' | 'stop'>();

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

window.addEventListener('DOMContentLoaded', () => {
  void renderStatus();
  const timer = window.setInterval(() => {
    if (pending.size === 0) void renderStatus();
  }, POLL_MS);
  window.addEventListener('beforeunload', () => window.clearInterval(timer));
});
