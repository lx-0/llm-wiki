// Health + update check — one `wiki doctor --json` call gives both the vault
// health summary AND whether an engine update is available (the
// `engine-update-available` check). Read-only; run on demand (it does a git fetch
// + connectivity probes, ~seconds), not on the fast poll.

import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin } from './wiki-exec';

export interface DoctorResult {
  /** critical + warning, EXCLUDING the engine-update-available check (that's surfaced as the update action) */
  issues: number;
  updateAvailable: boolean;
  /** e.g. "36 engine commits behind origin/main" */
  updateMessage?: string;
}

export function getDoctor(): Promise<DoctorResult | null> {
  return new Promise((resolve) => {
    const v = resolveVault();
    if (!v) return resolve(null);
    let out = '';
    const child = spawn(wikiBin(v.path), ['doctor', '--json'], {
      cwd: v.path,
      env: { ...process.env, PATH: augmentedPath() },
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    child.stdout.on('data', (b: Buffer) => (out += b.toString()));
    child.on('error', () => resolve(null));
    child.on('exit', () => {
      try {
        const d = JSON.parse(out);
        const checks: Array<{ id: string; severity: string }> = d.checks || [];
        const update = checks.find((c) => c.id === 'engine-update-available') as
          | { id: string; severity: string; message?: string }
          | undefined;
        const updateAvailable = !!update && (update.severity === 'warning' || /behind/i.test(update.message || ''));
        // health issues = critical+warning minus the update-available warning
        const sum = d.summary || { critical: 0, warning: 0 };
        const issues = (sum.critical || 0) + (sum.warning || 0) - (updateAvailable ? 1 : 0);
        resolve({
          issues: Math.max(0, issues),
          updateAvailable,
          updateMessage: updateAvailable ? update?.message : undefined,
        });
      } catch {
        resolve(null);
      }
    });
  });
}
