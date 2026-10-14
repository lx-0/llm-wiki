// Stub preload for the screenshot harness — replaces src/preload.ts with fixture-backed
// implementations of the same four window.* domains. The fixture state comes in via
// `webPreferences.additionalArguments` (--shots-state=<name>). Registered renderer callbacks
// and requested panel heights are kept here so capture.cjs can fire events and read heights
// through `window.__shots`.

const { contextBridge } = require('electron');
const fixtures = require('./fixtures.cjs');

const stateArg = process.argv.find((a) => a.startsWith('--shots-state='));
const state = stateArg ? stateArg.slice('--shots-state='.length) : 'default';
const fx = fixtures.build(state);

// The panel marks entries modified since it was last open; pretend that was an hour ago so
// the youngest fixture entries render as new.
try {
  localStorage.setItem('recentSeenMs', String(Date.now() - 60 * 60 * 1000));
} catch {
  // storage unavailable on this origin — the dots just stay off
}

const callbacks = {};
const heights = [];
const later = (value) => Promise.resolve(value);
const subscribe = (name) => (cb) => {
  callbacks[name] = callbacks[name] ?? [];
  callbacks[name].push(cb);
};
const noop = () => {};

contextBridge.exposeInMainWorld('vault', {
  status: () => later(fx.vault.status),
  list: () => later(fx.vault.list),
  preview: (file) => later(fx.vault.preview(file)),
  collectors: () => later(fx.vault.collectors),
  triage: (showAll) => later(fx.vault.triage.filter((r) => showAll || r.status === 'pending')),
  triageAction: () => later({ ok: true, message: 'ok' }),
  openInObsidian: () => later({ ok: true }),
  openFile: noop,
  openFullDiskAccess: noop,
  doctor: () => later(fx.vault.doctor),
  query: () => new Promise((resolve) => setTimeout(() => resolve(fx.vault.query), 300)),
  menu: () => later(fx.vault.menu),
  run: () => later({ started: true }),
  runArgs: () => later({ started: true }),
  runStatus: () => later(fx.vault.runStatus),
  onRunProgress: subscribe('runProgress'),
  onRunDone: subscribe('runDone'),
  compile: () => later({ started: true }),
  compileStatus: () => later(fx.vault.compileStatus),
  onCompileProgress: subscribe('compileProgress'),
  onCompileDone: subscribe('compileDone'),
});

contextBridge.exposeInMainWorld('listeners', {
  status: () => later(fx.listeners),
  control: () => later({ ok: true }),
  timeline: (id) => later(id === 'screenpipe' ? fx.listenerTimeline : null),
});

contextBridge.exposeInMainWorld('panel', {
  onVisibility: (cb) => {
    subscribe('visibility')(cb);
    setTimeout(() => cb(true), 50);
  },
  resize: (height) => {
    heights.push(height);
  },
});

contextBridge.exposeInMainWorld('app', {
  getLoginItem: () => later(fx.app.loginItem),
  setLoginItem: (open) => later(open),
  quit: noop,
  openSettings: noop,
  openBrowse: noop,
  openOverview: noop,
  openTriage: noop,
  onboardingDone: noop,
});

contextBridge.exposeInMainWorld('__shots', {
  state,
  heights: () => heights.slice(),
  /** Fire a subscribed renderer callback (compileDone, runDone, …); returns listener count. */
  fire: (event, payload) => {
    const list = callbacks[event] ?? [];
    for (const cb of list) cb(payload);
    return list.length;
  },
});
