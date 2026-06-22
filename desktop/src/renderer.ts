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

// Minimal render of live listener status + start/stop control (UI polish is S03).
// The renderer only calls the contextBridge API — no Node, no engine.
let busy = false;

async function renderStatus(): Promise<void> {
  const el = document.getElementById('listeners');
  if (!el) return;
  try {
    const statuses = await window.listeners.status();
    el.innerHTML = '';
    for (const s of statuses) {
      const dot = !s.running ? '⏹ stopped' : s.zombieSuspected ? '⚠ zombie?' : '● running';
      const ch = (label: string, c: { fresh: boolean; ageSeconds: number | null }) =>
        `${label}: ${c.ageSeconds == null ? 'no data' : `${c.ageSeconds}s ago`}${c.fresh ? ' ✓' : ''}`;
      const li = document.createElement('li');
      li.innerHTML = `<strong>${s.id}</strong> — ${dot} · ${ch('mic', s.channels.mic)} · ${ch('sys', s.channels.system)} `;
      const btn = document.createElement('button');
      btn.textContent = s.running ? 'Stop' : 'Start';
      btn.disabled = busy;
      btn.addEventListener('click', () => void control(s.id, s.running ? 'stop' : 'start'));
      li.appendChild(btn);
      el.appendChild(li);
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
});
