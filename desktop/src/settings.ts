// Settings window renderer — separate page (settings.html), same preload, so
// `window.app` (login-item) is available. Kept intentionally small; grows as the
// app gains settings.
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
