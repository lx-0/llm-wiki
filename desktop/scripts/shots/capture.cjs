// Screenshot harness — renders every built renderer page under the stub preload and writes
// out/shots/<page>-<scheme>-<state>.png plus out/shots/report.json (panel heights, errors).
//
//   npm run shots          (= vite build -c vite.renderer.config.ts && electron scripts/shots/capture.cjs)
//
// Exit code 1 when any page logged an error, a strict page fails the layout audit, or the
// panel at rest asks for more height than main will give it — the harness doubles as a smoke
// test of the bundle. Offscreen windows have no vibrancy, so the panel gets a solid
// popover-like background per scheme.

const { app, BrowserWindow, nativeTheme } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { AUDIT_SCRIPT } = require('./audit.cjs');
const { layoutFailures, restHeightFailure } = require('./gates.cjs');

/** Every page is built on the token system, so every page is strict: clipped text fails the
 *  run there, not just overlap. (A page outside the set would be audited and reported only.) */
const STRICT_PAGES = new Set(['index', 'overview', 'settings', 'onboarding', 'browse', 'triage', 'smoke']);

app.commandLine.appendSwitch('force-device-scale-factor', '2');

const ROOT = path.resolve(__dirname, '..', '..');
const BUILT = path.join(ROOT, '.vite', 'renderer', 'main_window');
const OUT = path.join(ROOT, 'out', 'shots');
const PRELOAD = path.join(__dirname, 'stub-preload.cjs');

const SURFACES = [
  {
    page: 'index',
    w: 360,
    h: 280,
    schemes: ['light', 'dark'],
    states: [
      'fresh',
      'asked',
      'running',
      'failed',
      'no-access',
      'empty',
      'library-open',
      'health-open',
      'capture-open',
      'run-progress',
      'run-done',
      'sources-open',
      'tools-open',
      'add-open',
    ],
    settle: 1200,
    panel: true,
    /** main clamps the popover at PANEL_MAX_H — at rest the panel must fit without scrolling */
    restHeight: { state: 'fresh', max: 640 },
  },
  {
    page: 'onboarding',
    w: 460,
    h: 700,
    schemes: ['light', 'dark'],
    states: ['default', 'no-access', 'empty'],
    settle: 1000,
  },
  {
    page: 'settings',
    w: 400,
    h: 400,
    schemes: ['light', 'dark'],
    states: ['default', 'no-access'],
    settle: 1000,
  },
  { page: 'browse', w: 480, h: 620, schemes: ['light', 'dark'], states: ['default', 'empty'], settle: 1000 },
  { page: 'triage', w: 720, h: 760, schemes: ['light', 'dark'], states: ['default', 'empty'], settle: 1000 },
  {
    page: 'overview',
    w: 920,
    h: 780,
    schemes: ['light', 'dark'],
    states: ['default', 'empty', 'no-access', 'table', 'run-done'],
    settle: 1000,
  },
  { page: 'smoke', w: 600, h: 1040, schemes: ['light', 'dark'], states: ['default'], settle: 800 },
];

// Panel states that reuse the `default` fixtures and differ only by a script run after load.
const FIXTURE_FOR = {
  fresh: 'default',
  asked: 'default',
  failed: 'default',
  'library-open': 'default',
  'health-open': 'default',
  'capture-open': 'default',
  'run-done': 'default',
  'sources-open': 'default',
  'tools-open': 'default',
  'add-open': 'default',
  table: 'default',
};
const openSheet = (name) => `(async () => {
    document.querySelector('[data-sheet="${name}"]')?.click();
    ${wait(600)}
  })()`;
const openTile = (index) => `(async () => {
    document.querySelectorAll('.tile')[${index}]?.click();
    ${wait(500)}
  })()`;

const wait = (ms) => `await new Promise((r) => setTimeout(r, ${ms}));`;
const STATE_SCRIPTS = {
  asked: `(async () => {
    const input = document.getElementById('ask-input');
    input.value = 'who owns the Fleet onboarding deck?';
    input.dispatchEvent(new Event('input', { bubbles: true })); // framework bindings listen to input, not value
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    ${wait(900)}
  })()`,
  failed: `(async () => {
    document.querySelectorAll('.tile')[0]?.click();
    window.__shots.fire('compileDone', { ok: false, durationMs: 41000 });
    ${wait(600)}
  })()`,
  running: `(async () => {
    document.querySelectorAll('.tile')[0]?.click();
    ${wait(500)}
  })()`,
  'library-open': openTile(0),
  'health-open': openTile(1),
  'capture-open': openTile(2),
  'run-progress': `(async () => {
    window.__shots.fire('runProgress', { id: 'process-inbox', progress: { current: 2, total: 3 } });
    ${wait(400)}
  })()`,
  'run-done': `(async () => {
    window.__shots.fire('runDone', { id: 'process-inbox', result: { ok: true, durationMs: 4000 } });
    window.__shots.fire('runDone', { id: 'compile', result: { ok: false, durationMs: 9000 } });
    ${wait(600)}
  })()`,
  'sources-open': openSheet('sources'),
  'tools-open': openSheet('tools'),
  'add-open': openSheet('add'),
  table: `(async () => {
    document.querySelector('[data-view="table"]')?.click();
    ${wait(500)}
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
  let layout = { clipped: [], overlaps: [], offscreen: [] };
  try {
    layout = await wc.executeJavaScript(AUDIT_SCRIPT, true);
  } catch (error) {
    errors.push(`layout audit: ${error.message}`);
  }
  win.destroy();
  return { file, height, errors, layout };
}

async function main() {
  if (!fs.existsSync(path.join(BUILT, 'index.html'))) {
    console.error(`no built renderer at ${BUILT} — run \`npm run build:renderer\` first`);
    return 2;
  }
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  if (app.dock) app.dock.hide();

  const report = {
    generatedAt: new Date().toISOString(),
    panelHeights: {},
    errors: {},
    layout: {},
    layoutFailures: {},
    heightFailures: {},
    files: [],
  };
  let index = 0;
  for (const surface of SURFACES) {
    for (const scheme of surface.schemes) {
      for (const state of surface.states) {
        index += 1;
        const result = await shoot(surface, scheme, state, index);
        report.files.push(result.file);
        if (result.height != null) report.panelHeights[`${scheme}-${state}`] = result.height;
        if (result.errors.length) report.errors[result.file] = result.errors;
        report.layout[result.file] = result.layout;
        const failures = layoutFailures(STRICT_PAGES, surface.page, result.layout);
        if (failures.length) report.layoutFailures[result.file] = failures;
        const tooTall = restHeightFailure(surface, scheme, state, result.height);
        if (tooTall) report.heightFailures[result.file] = tooTall;
        console.log(
          `${result.file}${result.height != null ? `  height=${result.height}` : ''}${result.errors.length ? `  ERRORS=${result.errors.length}` : ''}${failures.length ? `  LAYOUT=${failures.length}` : ''}${tooTall ? '  TOO TALL' : ''}`,
        );
      }
    }
  }
  fs.writeFileSync(path.join(OUT, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  const failed = Object.keys(report.errors).length;
  const broken = Object.keys(report.layoutFailures).length;
  const tall = Object.keys(report.heightFailures).length;
  console.log(
    `\n${report.files.length} screenshots → ${OUT}${failed ? `\n${failed} page(s) logged errors — see report.json` : ''}${broken ? `\n${broken} page(s) failed the layout gate — see report.json layoutFailures` : ''}${tall ? `\n${tall} panel state(s) exceed the rest-height budget — see report.json heightFailures` : ''}`,
  );
  return failed || broken || tall ? 1 : 0;
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
