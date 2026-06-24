// First-run onboarding window — detects the library, walks the macOS Full-Disk-Access
// grant (the #1 stumbling block, since the library is in iCloud Drive), discloses the
// background capture (with an opt-out), and offers start-at-login. Same preload, so
// window.vault / window.app / window.listeners are available.
import './index.css';

const vaultDetail = document.getElementById('vault-detail');
const stepAccess = document.getElementById('step-access');
const stepCapture = document.getElementById('step-capture');
const captureToggle = document.getElementById('capture-toggle') as HTMLInputElement | null;
let captureId = '';

/** Renumber the visible steps 1..N — steps are conditional (access only when the
 *  library is unreadable; capture only when a capture process exists). */
function renumber(): void {
  const steps = [...document.querySelectorAll('.ob-step')].filter((s) => !(s as HTMLElement).hidden);
  steps.forEach((s, i) => {
    const n = s.querySelector('.ob-num');
    if (n) n.textContent = String(i + 1);
  });
}

async function loadVault(): Promise<void> {
  const v = await window.vault.status();
  if (!v) {
    if (vaultDetail) vaultDetail.textContent = 'No library found yet — set one up with the wiki CLI first.';
    if (stepAccess) stepAccess.hidden = true;
  } else {
    if (vaultDetail) vaultDetail.innerHTML = `<b>${v.name}</b> · ${v.articleCount.toLocaleString()} notes`;
    // the file-access step only matters when we can't actually read the library
    if (stepAccess) stepAccess.hidden = v.accessible;
  }
  renumber();
}

async function loadCapture(): Promise<void> {
  try {
    const statuses = await window.listeners.status();
    const cap = statuses[0];
    if (!cap) {
      if (stepCapture) stepCapture.hidden = true;
    } else {
      captureId = cap.id;
      if (stepCapture) stepCapture.hidden = false;
      if (captureToggle) captureToggle.checked = cap.running;
    }
  } catch {
    if (stepCapture) stepCapture.hidden = true;
  }
  renumber();
}

captureToggle?.addEventListener('change', () => {
  if (!captureId) return;
  void window.listeners.control(captureId, captureToggle.checked ? 'start' : 'stop').then((res) => {
    if (!res.ok) captureToggle.checked = !captureToggle.checked; // revert on failure
  });
});

document.getElementById('open-fda')?.addEventListener('click', () => window.vault.openFullDiskAccess());
document.getElementById('recheck')?.addEventListener('click', () => void loadVault());

const toggle = document.getElementById('login-toggle') as HTMLInputElement | null;
void window.app.getLoginItem().then((on) => {
  if (toggle) toggle.checked = on;
});
toggle?.addEventListener('change', () => {
  void window.app.setLoginItem(toggle.checked).then((actual) => {
    toggle.checked = actual;
  });
});

document.getElementById('done')?.addEventListener('click', () => window.app.onboardingDone());

void loadVault();
void loadCapture();
