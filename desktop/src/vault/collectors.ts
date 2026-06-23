// Substrate collectors — `wiki collect --list` (the intake sources: email, calendar,
// meetings, voice, …). Surfaced as a "Sync sources" list so the app can pull from the
// configured accounts, not just ingest URLs. Read on demand (spawns the wiki CLI).

import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin, ANSI } from './wiki-exec';

export interface Collector {
  name: string;
  configured: boolean;
}

export function listCollectors(): Promise<Collector[]> {
  return new Promise((resolve) => {
    const v = resolveVault();
    if (!v) return resolve([]);
    let out = '';
    const child = spawn(wikiBin(v.path), ['collect', '--list'], {
      cwd: v.path,
      env: { ...process.env, PATH: augmentedPath() },
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    child.stdout.on('data', (b: Buffer) => (out += b.toString()));
    child.on('error', () => resolve([]));
    child.on('exit', () => {
      const collectors: Collector[] = [];
      for (const line of out.replace(ANSI, '').split('\n')) {
        const m = line.match(/^(\S+)\s+(✓|✗)/); // NAME  ✓/✗  (header/divider rows don't match)
        if (m) collectors.push({ name: m[1], configured: m[2] === '✓' });
      }
      resolve(collectors);
    });
  });
}
