// Shared helpers for spawning the vault's `wiki` CLI. A launchd/Finder-launched
// app has a minimal PATH (no Homebrew/asdf), and the `wiki` wrapper needs `uv`.

import os from 'node:os';
import path from 'node:path';

export function augmentedPath(): string {
  return [
    '/opt/homebrew/bin',
    path.join(os.homedir(), '.local', 'bin'),
    path.join(os.homedir(), '.asdf', 'shims'),
    '/usr/local/bin',
    process.env.PATH || '',
  ].join(':');
}

export function wikiBin(vaultPath: string): string {
  return path.join(vaultPath, '.wiki', 'wiki');
}

/** Strip ANSI escape codes from CLI output before showing it in the UI. */
// eslint-disable-next-line no-control-regex
export const ANSI = /\x1b\[[0-9;]*m/g;
