import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Every renderer page shares one preload + one bundle output dir. `base` + `outDir` repeat
// Forge's own renderer defaults (plugin-vite/dist/config/vite.renderer.config.js) so that a
// standalone `vite build -c vite.renderer.config.ts` (used by `npm run shots`) produces the
// same bundle Forge packages.
// https://vitejs.dev/config
export default defineConfig({
  base: './',
  build: {
    outDir: '.vite/renderer/main_window',
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        settings: resolve(__dirname, 'settings.html'),
        onboarding: resolve(__dirname, 'onboarding.html'),
        browse: resolve(__dirname, 'browse.html'),
        cockpit: resolve(__dirname, 'cockpit.html'),
        atlas: resolve(__dirname, 'atlas.html'),
        triage: resolve(__dirname, 'triage.html'),
      },
    },
  },
});
