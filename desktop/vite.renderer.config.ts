import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Two renderer pages: the menubar panel (index.html) + the Settings window
// (settings.html). Both share the same preload + bundle output dir.
// https://vitejs.dev/config
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        settings: resolve(__dirname, 'settings.html'),
        onboarding: resolve(__dirname, 'onboarding.html'),
      },
    },
  },
});
