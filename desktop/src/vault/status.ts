// Vault status — filesystem-derived facts about the active vault (no engine call;
// same "app reads system directly" lane as listener status). Richer pipeline
// stats (last compile, dream health) would need the engine bridge — deferred.

import fs from 'node:fs';
import path from 'node:path';
import { resolveVault } from './registry';

export interface VaultStatus {
  name: string;
  path: string;
  /** count of markdown articles under knowledge/ (excluding index.md) */
  articleCount: number;
  /** newest article mtime under knowledge/, epoch ms (null if none) */
  lastActivityMs: number | null;
}

function walk(dir: string, acc: { count: number; newest: number }): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      walk(full, acc);
    } else if (e.name.endsWith('.md') && e.name !== 'index.md') {
      acc.count++;
      try {
        const m = fs.statSync(full).mtimeMs;
        if (m > acc.newest) acc.newest = m;
      } catch {
        /* skip unreadable */
      }
    }
  }
}

export function getVaultStatus(): VaultStatus | null {
  const v = resolveVault();
  if (!v) return null;
  const acc = { count: 0, newest: 0 };
  walk(path.join(v.path, 'knowledge'), acc);
  return {
    name: v.name,
    path: v.path,
    articleCount: acc.count,
    lastActivityMs: acc.newest || null,
  };
}
