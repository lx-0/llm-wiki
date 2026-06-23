// Health + update check — one `wiki doctor --json` call gives both the vault
// health summary AND whether an engine update is available (the
// `engine-update-available` check). Read-only; run on demand (it does a git fetch
// + connectivity probes, ~seconds), not on the fast poll.

import { spawn } from 'node:child_process';
import { resolveVault } from './registry';
import { augmentedPath, wikiBin } from './wiki-exec';

export interface DoctorCheck {
  id: string;
  severity: string; // 'critical' | 'warning'
  message: string;
  /** human fix hint, e.g. "wiki gmail-auth gmail-personal" */
  fix?: string;
  /** engine args that fix it (if the engine offers a one-shot), e.g. ["lint","--structural-only"] */
  dispatchArgs?: string[];
}

export interface DoctorResult {
  /** critical + warning, EXCLUDING the engine-update-available check (that's surfaced as the update action) */
  issues: number;
  updateAvailable: boolean;
  /** e.g. "36 engine commits behind origin/main" */
  updateMessage?: string;
  /** the individual non-ok checks (critical + warning, minus the update one) */
  checks: DoctorCheck[];
}

interface RawCheck {
  id: string;
  severity: string;
  message?: string;
  fix?: string;
  dispatch_args?: string[] | null;
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
        const raw: RawCheck[] = Array.isArray(d.checks) ? d.checks : [];
        const update = raw.find((c) => c.id === 'engine-update-available');
        const updateAvailable = !!update && (update.severity === 'warning' || /behind/i.test(update.message || ''));
        // The actionable issues: critical + warning, minus the update-available one.
        const checks: DoctorCheck[] = raw
          .filter((c) => (c.severity === 'critical' || c.severity === 'warning') && c.id !== 'engine-update-available')
          .map((c) => ({
            id: c.id,
            severity: c.severity,
            message: c.message || c.id,
            fix: c.fix || undefined,
            dispatchArgs: Array.isArray(c.dispatch_args) ? c.dispatch_args : undefined,
          }));
        resolve({
          issues: checks.length,
          updateAvailable,
          updateMessage: updateAvailable ? update?.message : undefined,
          checks,
        });
      } catch {
        resolve(null);
      }
    });
  });
}
