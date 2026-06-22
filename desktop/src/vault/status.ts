// Vault status — filesystem-derived facts about the active vault (no engine call;
// same "app reads system directly" lane as listener status). Richer pipeline
// stats (last compile, dream health) would need the engine bridge — deferred.

import fs from 'node:fs';
import path from 'node:path';
import { resolveVault } from './registry';

export interface RecentEntry {
  /** display title (first H1, else slug) */
  title: string;
  /** path relative to the vault root, for an obsidian:// open link */
  file: string;
  mtimeMs: number;
}

export interface VaultStatus {
  name: string;
  path: string;
  /** count of markdown articles under knowledge/ (excluding index.md) */
  articleCount: number;
  /** newest article mtime under knowledge/, epoch ms (null if none) */
  lastActivityMs: number | null;
  /** the most recently modified articles (newest first), for the "Recent" list */
  recent: RecentEntry[];
  /** false if reading the vault was blocked (TCC / Full Disk Access) */
  accessible: boolean;
}

const RECENT_COUNT = 5;

function walk(dir: string, files: { full: string; mtimeMs: number }[]): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      walk(full, files);
    } else if (e.name.endsWith('.md') && e.name !== 'index.md') {
      try {
        files.push({ full, mtimeMs: fs.statSync(full).mtimeMs });
      } catch {
        /* skip unreadable */
      }
    }
  }
}

/** First H1 of a markdown file, else its slug (dashes → spaces). */
function titleOf(full: string): string {
  try {
    const m = fs.readFileSync(full, 'utf8').match(/^#\s+(.+?)\s*$/m);
    if (m) return m[1].trim();
  } catch {
    /* fall through to slug */
  }
  return (path.basename(full, '.md') || full).replace(/-/g, ' ');
}

export function getVaultStatus(): VaultStatus | null {
  const v = resolveVault();
  if (!v) return null;

  // Distinguish "blocked" from "empty": if we can't even enumerate knowledge/,
  // the app lacks file access (TCC / Full Disk Access — the vault is often under
  // iCloud Drive, which a Finder-launched .app can't read without the grant).
  const knowledge = path.join(v.path, 'knowledge');
  let accessible = true;
  try {
    fs.readdirSync(knowledge);
  } catch {
    accessible = false;
  }

  const files: { full: string; mtimeMs: number }[] = [];
  if (accessible) walk(knowledge, files);
  files.sort((a, b) => b.mtimeMs - a.mtimeMs);
  const recent: RecentEntry[] = files.slice(0, RECENT_COUNT).map((f) => ({
    title: titleOf(f.full),
    file: path.relative(v.path, f.full),
    mtimeMs: f.mtimeMs,
  }));

  return {
    name: v.name,
    path: v.path,
    articleCount: files.length,
    lastActivityMs: files[0]?.mtimeMs ?? null,
    recent,
    accessible,
  };
}
