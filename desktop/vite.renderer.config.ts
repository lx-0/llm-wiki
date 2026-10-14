import { resolve } from 'node:path';
import { defineConfig } from 'vite';

/** One HTML entry per window; main.ts loads them by the same names. */
const PAGES = ['index', 'settings', 'onboarding', 'browse', 'cockpit', 'atlas', 'triage'];

// Every renderer page shares one preload + one bundle output dir. `base` + `outDir` repeat
// Forge's own renderer defaults so that a standalone `vite build -c vite.renderer.config.ts`
// (used by `npm run shots`) produces the same bundle Forge packages.
// https://vitejs.dev/config
export default defineConfig({
  base: './',
  build: {
    outDir: '.vite/renderer/main_window',
    rolldownOptions: {
      input: Object.fromEntries(PAGES.map((page) => [page, resolve(import.meta.dirname, `${page}.html`)])),
    },
  },
});
