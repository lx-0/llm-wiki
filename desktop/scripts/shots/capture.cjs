// Screenshot harness — renders every built renderer page under the stub preload and writes
// out/shots/<page>-<scheme>-<state>.png plus out/shots/report.json (panel heights, errors).
//
//   npm run shots          (= vite build -c vite.renderer.config.ts && electron scripts/shots/capture.cjs)
//
// Exit code 1 when any page logged an error — the harness doubles as a smoke test of the
// bundle. Offscreen windows have no vibrancy, so the panel gets a solid popover-like
// background per scheme.

const { app, BrowserWindow, nativeTheme } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

app.commandLine.appendSwitch('force-device-scale-factor', '2');

const ROOT = path.resolve(__dirname, '..', '..');
const BUILT = path.join(ROOT, '.vite', 'renderer', 'main_window');
const OUT = path.join(ROOT, 'out', 'shots');
const PRELOAD = path.join(__dirname, 'stub-preload.cjs');

const SURFACES = [
  { page: 'index', w: 360, h: 280, schemes: ['light', 'dark'], states: ['fresh', 'asked', 'expanded', 'running', 'failed', 'no-access', 'empty'], settle: 1200, panel: true },
  { page: 'onboarding', w: 460, h: 700, schemes: ['light', 'dark'], states: ['default'], settle: 1000 },
  { page: 'settings', w: 400, h: 400, schemes: ['light', 'dark'], states: ['default'], settle: 1000 },
  { page: 'browse', w: 480, h: 620, schemes: ['light', 'dark'], states: ['default', 'empty'], settle: 1000 },
  { page: 'triage', w: 720, h: 760, schemes: ['light', 'dark'], states: ['default', 'empty'], settle: 1000 },
  { page: 'cockpit', w: 1040, h: 700, schemes: ['dark'], states: ['default'], settle: 3500 },
  { page: 'atlas', w: 1100, h: 720, schemes: ['dark'], states: ['default'], settle: 3500 },
];

// Panel states that reuse the `default` fixtures and differ only by a script run after load.
const FIXTURE_FOR = { fresh: 'default', asked: 'default', expanded: 'default', failed: 'default' };

const wait = (ms) => `await new Promise((r) => setTimeout(r, ${ms}));`;
const STATE_SCRIPTS = {
  asked: `(async () => {
    const input = document.getElementById('ask-input');
    input.value = 'who owns the Fleet onboarding deck?';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    ${wait(900)}
  })()`,
  expanded: `(async () => {
    document.getElementById('nav-hint-x')?.click();
    document.querySelector('.health-row.clickable')?.click();
    for (const id of ['sources', 'advanced']) { const d = document.getElementById(id); if (d) d.open = true; }
    ${wait(900)}
  })()`,
  failed: `(async () => {
    window.__shots.fire('compileDone', { ok: false, durationMs: 41000 });
    ${wait(400)}
  })()`,
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function shoot(surface, scheme, state, index) {
  nativeTheme.themeSource = scheme;
  const errors = [];
  const win = new BrowserWindow({
    width: surface.w,
    height: surface.h,
    show: false,
    frame: false,
    backgroundColor: surface.panel ? (scheme === 'dark' ? '#1c1c1e' : '#f6f6f8') : undefined,
    webPreferences: {
      preload: PRELOAD,
      sandbox: false,
      contextIsolation: true,
      offscreen: true,
      additionalArguments: [`--shots-state=${FIXTURE_FOR[state] ?? state}`],
      partition: `shots-${index}`,
    },
  });
  const wc = win.webContents;
  wc.on('console-message', (event) => {
    if (event.level === 'error') errors.push(event.message);
  });
  wc.on('preload-error', (_event, _preloadPath, error) => errors.push(`preload: ${error.message}`));
  wc.on('render-process-gone', (_event, details) => errors.push(`render process gone: ${details.reason}`));

  await win.loadFile(path.join(BUILT, `${surface.page}.html`));
  await sleep(surface.settle);
  try {
    if (STATE_SCRIPTS[state]) await wc.executeJavaScript(STATE_SCRIPTS[state], true);
  } catch (error) {
    errors.push(`state script ${state}: ${error.message}`);
  }

  let height = null;
  if (surface.panel) {
    const heights = await wc.executeJavaScript('window.__shots.heights()', true);
    if (heights.length) {
      height = Math.ceil(heights[heights.length - 1]);
      win.setSize(surface.w, Math.max(surface.h, height));
      await sleep(300);
    }
  }

  const image = await wc.capturePage();
  const file = `${surface.page}-${scheme}-${state}.png`;
  fs.writeFileSync(path.join(OUT, file), image.toPNG());
  win.destroy();
  return { file, height, errors };
}

async function main() {
  if (!fs.existsSync(path.join(BUILT, 'index.html'))) {
    console.error(`no built renderer at ${BUILT} — run \`npm run build:renderer\` first`);
    return 2;
  }
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  if (app.dock) app.dock.hide();

  const report = { generatedAt: new Date().toISOString(), panelHeights: {}, errors: {}, files: [] };
  let index = 0;
  for (const surface of SURFACES) {
    for (const scheme of surface.schemes) {
      for (const state of surface.states) {
        index += 1;
        const result = await shoot(surface, scheme, state, index);
        report.files.push(result.file);
        if (result.height != null) report.panelHeights[`${scheme}-${state}`] = result.height;
        if (result.errors.length) report.errors[result.file] = result.errors;
        console.log(`${result.file}${result.height != null ? `  height=${result.height}` : ''}${result.errors.length ? `  ERRORS=${result.errors.length}` : ''}`);
      }
    }
  }
  fs.writeFileSync(path.join(OUT, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  const failed = Object.keys(report.errors).length;
  console.log(`\n${report.files.length} screenshots → ${OUT}${failed ? `\n${failed} page(s) logged errors — see report.json` : ''}`);
  return failed ? 1 : 0;
}

app.on('window-all-closed', () => {});
app
  .whenReady()
  .then(main)
  .then((code) => app.exit(code))
  .catch((error) => {
    console.error(error);
    app.exit(1);
  });
