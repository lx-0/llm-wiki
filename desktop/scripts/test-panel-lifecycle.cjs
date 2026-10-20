// Real Electron lifecycle regression. Run after `npm run package` on a desktop.
// Uses a disposable HOME/userData so neither the operator's vault nor login settings run.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { app, BrowserWindow } = require('electron');

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'wiki-panel-lifecycle-'));
process.env.HOME = scratch;
process.env.XDG_CONFIG_HOME = path.join(scratch, '.config');
app.setPath('userData', scratch);
fs.writeFileSync(path.join(scratch, 'onboarded'), 'test');
fs.mkdirSync(path.join(scratch, '.screenpipe'));
execFileSync('sqlite3', [
  path.join(scratch, '.screenpipe', 'db.sqlite'),
  'CREATE TABLE audio_chunks (timestamp TEXT, file_path TEXT);',
]);

async function dismiss(win) {
  const finished = new Promise((resolve) => {
    win.once('close', (event) => {
      if (event.defaultPrevented) resolve();
      else win.once('closed', resolve);
    });
  });
  win.close();
  await finished;
}

let panel;
let tested = false;
const deadline = setTimeout(() => {
  console.error('FAIL: panel lifecycle did not finish in 20 seconds');
  app.exit(1);
}, 20_000);

app.on('quit', () => {
  clearTimeout(deadline);
  fs.rmSync(scratch, { recursive: true, force: true });
});

require('../.vite/build/main.cjs');

app.whenReady().then(async () => {
  try {
    const windows = BrowserWindow.getAllWindows();
    assert.equal(windows.length, 1, 'only the panel should open after onboarding');
    panel = windows[0];
    if (panel.webContents.isLoading()) await once(panel.webContents, 'did-finish-load');

    panel.showInactive();
    await dismiss(panel);
    assert.equal(panel.isDestroyed(), false, 'closing the panel must not destroy the tray app UI');
    assert.equal(panel.isVisible(), false, 'closing dismisses the panel');

    panel.showInactive();
    assert.equal(panel.isVisible(), true, 'the same panel can reopen after dismissal');
    await dismiss(panel);
    assert.equal(panel.isDestroyed(), false, 'repeated dismissal keeps the panel alive');
    tested = true;
    app.quit();
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});

app.on('will-quit', () => {
  try {
    assert.equal(tested, true, 'dismiss/reopen checks completed before quitting');
    assert.equal(panel.isDestroyed(), true, 'Quit must still destroy the panel and exit');
    console.log('PASS: dismiss, reopen, dismiss again, and Quit');
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});
