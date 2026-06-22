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
let busy = false;
const POLL_MS = 3000;

function fmtAge(c: { fresh: boolean; ageSeconds: number | null }): string {
  if (c.ageSeconds == null) return 'no data';
  const a = c.ageSeconds < 90 ? `${c.ageSeconds}s` : `${Math.round(c.ageSeconds / 60)}m`;
  return `${a} ago${c.fresh ? ' ✓' : ''}`;
}

function fmtClock(ms: number | null): string {
  return ms == null ? '—' : new Date(ms).toLocaleTimeString();
}

async function renderStatus(): Promise<void> {
  const el = document.getElementById('listeners');
  if (!el) return;
  try {
    const statuses = await window.listeners.status();
    el.innerHTML = '';
    for (const s of statuses) {
      const state = !s.running ? 'stopped' : s.zombieSuspected ? 'zombie' : 'running';
      const card = document.createElement('li');
      card.className = 'listener';
      card.innerHTML = `
        <div class="row">
          <span class="dot ${state}"></span>
          <strong>${s.id}</strong>
          <span class="state ${state}">${state}</span>
        </div>
        <div class="channels">
          <span>mic: ${fmtAge(s.channels.mic)}</span>
          <span>sys: ${fmtAge(s.channels.system)}</span>
          <span class="muted">last: ${fmtClock(s.channels.mic.lastCaptureAtMs)}</span>
        </div>`;
      const btn = document.createElement('button');
      btn.textContent = s.running ? 'Stop' : 'Start';
      btn.disabled = busy;
      btn.addEventListener('click', () => void control(s.id, s.running ? 'stop' : 'start'));
      card.querySelector('.row')?.appendChild(btn);
      el.appendChild(card);
    }
  } catch (err) {
    el.textContent = `status error: ${String(err)}`;
    console.error(err);
  }
}

async function control(id: string, action: 'start' | 'stop'): Promise<void> {
  if (busy) return;
  busy = true;
  void renderStatus(); // reflect disabled buttons
  try {
    const res = await window.listeners.control(id, action);
    if (!res.ok) console.error(`${action} ${id} failed:`, res.error);
  } finally {
    busy = false;
    void renderStatus();
  }
}

window.addEventListener('DOMContentLoaded', () => {
  void renderStatus();
  const timer = window.setInterval(() => {
    if (!busy) void renderStatus();
  }, POLL_MS);
  window.addEventListener('beforeunload', () => window.clearInterval(timer));
});
