import { FuseV1Options, FuseVersion } from '@electron/fuses';
import { MakerDeb } from '@electron-forge/maker-deb';
import { MakerDMG } from '@electron-forge/maker-dmg';
import { MakerRpm } from '@electron-forge/maker-rpm';
import { MakerSquirrel } from '@electron-forge/maker-squirrel';
import { MakerZIP } from '@electron-forge/maker-zip';
import { FusesPlugin } from '@electron-forge/plugin-fuses';
import { VitePlugin } from '@electron-forge/plugin-vite';
import type { ForgeConfig } from '@electron-forge/shared-types';

// macOS signing/notarization is env-gated so `npm run package` works WITHOUT
// credentials (unsigned dev build), and signs only when the operator's Apple
// Developer ID env vars are present. Prereqs (operator-provided):
//   APPLE_ID                — Apple Developer account email
//   APPLE_PASSWORD          — app-specific password (appleid.apple.com)
//   APPLE_TEAM_ID           — Developer team id
// A "Developer ID Application" cert must be in the login keychain.
// See https://www.electronforge.io/guides/code-signing/code-signing-macos
const { APPLE_ID, APPLE_PASSWORD, APPLE_TEAM_ID } = process.env;
const signing =
  APPLE_ID && APPLE_PASSWORD && APPLE_TEAM_ID
    ? {
        osxSign: {},
        osxNotarize: { appleId: APPLE_ID, appleIdPassword: APPLE_PASSWORD, teamId: APPLE_TEAM_ID },
      }
    : {};

const config: ForgeConfig = {
  packagerConfig: {
    asar: true,
    name: 'llm-wiki',
    icon: 'assets/icon', // forge appends .icns on macOS (assets/icon.icns)
    // Stable app identity (not the generic com.github.Electron). Matters for TCC
    // grants the app may need later. Operator can rename to an org-preferred id.
    appBundleId: 'cloud.yesterday.llm-wiki',
    ...signing,
  },
  rebuildConfig: {},
  makers: [
    new MakerSquirrel({}),
    new MakerZIP({}, ['darwin']),
    new MakerDMG({ name: 'llm-wiki' }, ['darwin']),
    new MakerRpm({}),
    new MakerDeb({}),
  ],
  plugins: [
    new VitePlugin({
      // `build` can specify multiple entry builds, which can be Main process, Preload scripts, Worker process, etc.
      // If you are familiar with Vite configuration, it will look really familiar.
      build: [
        {
          // `entry` is just an alias for `build.lib.entry` in the corresponding file of `config`.
          entry: 'src/main.ts',
          config: 'vite.main.config.ts',
          target: 'main',
        },
        {
          entry: 'src/preload.ts',
          config: 'vite.preload.config.ts',
          target: 'preload',
        },
      ],
      renderer: [
        {
          name: 'main_window',
          config: 'vite.renderer.config.ts',
        },
      ],
    }),
    // Fuses are used to enable/disable various Electron functionality
    // at package time, before code signing the application
    new FusesPlugin({
      version: FuseVersion.V1,
      [FuseV1Options.RunAsNode]: false,
      [FuseV1Options.EnableCookieEncryption]: true,
      [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
      [FuseV1Options.EnableNodeCliInspectArguments]: false,
      [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
      [FuseV1Options.OnlyLoadAppFromAsar]: true,
    }),
  ],
};

export default config;
