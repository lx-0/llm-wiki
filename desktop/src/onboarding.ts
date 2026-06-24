// First-run onboarding window — detects the vault, walks the macOS Full-Disk-Access
// grant (the #1 stumbling block, since the vault is in iCloud Drive), and offers
// start-at-login. Same preload, so window.vault / window.app are available.
import './index.css';

const vaultDetail = document.getElementById('vault-detail');
const stepAccess = document.getElementById('step-access');
const loginNum = document.getElementById('login-num');

async function loadVault(): Promise<void> {
  const v = await window.vault.status();
  if (!v) {
    if (vaultDetail) vaultDetail.textContent = 'No library found yet — set one up with the wiki CLI first.';
    if (stepAccess) stepAccess.hidden = true;
    return;
  }
  if (vaultDetail) vaultDetail.innerHTML = `<b>${v.name}</b> · ${v.articleCount.toLocaleString()} notes`;
  // The file-access step only matters when we can't actually read the vault.
  if (stepAccess) stepAccess.hidden = v.accessible;
  if (loginNum) loginNum.textContent = v.accessible ? '2' : '3';
}

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
