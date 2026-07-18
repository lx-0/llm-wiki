// Health + update check — one `wiki doctor --json` call gives both the vault
// health summary AND whether an engine update is available (the
// `engine-update-available` check). Read-only; run on demand (it does a git fetch
// + connectivity probes, ~seconds), not on the fast poll. Goes through the shared
// runWiki runner, which caps the git-fetch probe so it can't hang forever.

import { runWiki, parseJson } from './wiki-exec';

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

/** git fetch + connectivity probes: "~seconds", but capped so a dead network can't
 *  leave getDoctor()'s promise pending forever. */
const DOCTOR_TIMEOUT_MS = 60_000;

/** Shape `wiki doctor --json` into the app's DoctorResult. Throws on malformed JSON
 *  (runWiki's parse-with-fallback then yields data=null → getDoctor returns null). */
export function parseDoctor(stdout: string): DoctorResult {
  const d = parseJson<{ checks?: RawCheck[] }>(stdout);
  const raw: RawCheck[] = Array.isArray(d.checks) ? d.checks : [];
  const update = raw.find((c) => c.id === 'engine-update-available');
  const updateAvailable =
    !!update && (update.severity === 'warning' || /behind/i.test(update.message || ''));
  // The actionable issues: critical + warning, minus the update-available one.
  const checks: DoctorCheck[] = raw
    .filter(
      (c) =>
        (c.severity === 'critical' || c.severity === 'warning') &&
        c.id !== 'engine-update-available',
    )
    .map((c) => ({
      id: c.id,
      severity: c.severity,
      message: c.message || c.id,
      fix: c.fix || undefined,
      dispatchArgs: Array.isArray(c.dispatch_args) ? c.dispatch_args : undefined,
    }));
  return {
    issues: checks.length,
    updateAvailable,
    updateMessage: updateAvailable ? update?.message : undefined,
    checks,
  };
}

export async function getDoctor(): Promise<DoctorResult | null> {
  const r = await runWiki(['doctor', '--json'], {
    parse: parseDoctor,
    timeout: DOCTOR_TIMEOUT_MS,
  });
  return r.data;
}
