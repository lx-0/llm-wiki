// Settings window renderer — separate page (settings.html), same preload, so
// window.app / window.vault / window.listeners are available. A status + control
// panel: vault info, file-access state, capture state, start-at-login.
import './index.css';

const toggle = document.getElementById('login-toggle') as HTMLInputElement | null;

void window.app.getLoginItem().then((on) => {
  if (toggle) toggle.checked = on;
});

toggle?.addEventListener('change', () => {
  void window.app.setLoginItem(toggle.checked).then((actual) => {
    toggle.checked = actual; // reflect the real registered state
    toggle.title =
      actual === toggle.checked
        ? ''
        : 'Login items register only for the installed app (drag to Applications) — not in dev mode';
  });
});

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}

async function loadStatus(): Promise<void> {
  const v = await window.vault.status();
  const vaultEl = document.getElementById('set-vault');
  const openBtn = document.getElementById('set-open') as HTMLButtonElement | null;
  const fdaSub = document.getElementById('fda-sub');
  const fdaBtn = document.getElementById('fda-btn') as HTMLButtonElement | null;

  if (vaultEl) {
    vaultEl.innerHTML = v
      ? `<b>${esc(v.name)}</b> · ${v.articleCount.toLocaleString()} notes<div class="set-path" title="${esc(v.path)}">${esc(v.path.replace(/^\/Users\/[^/]+/, '~'))}</div>`
      : 'No library found yet — set one up with the wiki CLI first.';
  }
  if (openBtn) openBtn.hidden = !v;

  const ok = v?.accessible;
  if (fdaSub) {
    fdaSub.textContent = !v
      ? '—'
      : ok
        ? 'Granted — llm-wiki can read your library'
        : "Not granted — llm-wiki can't read your iCloud vault yet";
  }
  if (fdaBtn) fdaBtn.hidden = !v || !!ok;

  const capSub = document.getElementById('cap-sub');
  if (capSub) {
    try {
      const ls = await window.listeners.status();
      const sp = ls[0];
      capSub.textContent = !sp
        ? 'Not configured'
        : sp.running
          ? 'Recording — your screen, mic + system audio'
          : 'Stopped';
    } catch {
      capSub.textContent = '—';
    }
  }
}

document.getElementById('set-open')?.addEventListener('click', () => void window.vault.openInObsidian());
document.getElementById('fda-btn')?.addEventListener('click', () => window.vault.openFullDiskAccess());

void loadStatus();
