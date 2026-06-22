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

// Minimal render of live listener status (UI polish is S03). The renderer only
// calls the contextBridge API — no Node, no engine.
async function renderStatus(): Promise<void> {
  const el = document.getElementById('listeners');
  if (!el) return;
  try {
    const statuses = await window.listeners.status();
    el.innerHTML = statuses
      .map((s) => {
        const dot = !s.running ? '⏹ stopped' : s.zombieSuspected ? '⚠ zombie?' : '● running';
        const ch = (label: string, c: { fresh: boolean; ageSeconds: number | null }) =>
          `${label}: ${c.ageSeconds == null ? 'no data' : `${c.ageSeconds}s ago`}${c.fresh ? ' ✓' : ''}`;
        return `<li><strong>${s.id}</strong> — ${dot} · ${ch('mic', s.channels.mic)} · ${ch('sys', s.channels.system)}</li>`;
      })
      .join('');
  } catch (err) {
    el.textContent = `status error: ${String(err)}`;
    console.error(err);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  void renderStatus();
});
