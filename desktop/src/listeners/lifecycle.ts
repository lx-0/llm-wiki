// Listener lifecycle actions — start / stop / restart a launchd-managed daemon.
// Ported from the verified ~/.screenpipe/sp prototype, but self-contained (the
// prototype is NOT called at runtime). System control only; no engine involvement.

import { execFileSync } from 'node:child_process';
import type { ListenerDef } from './registry';
import { isRunning } from './status';

export type LifecycleAction = 'start' | 'stop' | 'restart';

export interface LifecycleResult {
  action: LifecycleAction;
  ok: boolean;
  /** true if nothing needed doing (already in target state) */
  noop?: boolean;
  error?: string;
}

/** launchd gui-domain service target, e.g. `gui/501/com.alex.screenpipe` (pure). */
export function guiDomainTarget(uid: number, label: string): string {
  return `gui/${uid}/${label}`;
}

/** launchd gui domain, e.g. `gui/501` (pure). */
export function guiDomain(uid: number): string {
  return `gui/${uid}`;
}

function run(args: string[]): void {
  execFileSync('launchctl', args, { stdio: 'ignore' });
}

function uid(): number {
  // process.getuid exists on macOS/Linux; fall back to 0 only defensively.
  return typeof process.getuid === 'function' ? process.getuid() : 0;
}

/** Start (bootstrap) the listener. No-op if already running. */
export function startListener(def: ListenerDef): LifecycleResult {
  if (isRunning(def.launchdLabel)) return { action: 'start', ok: true, noop: true };
  try {
    run(['bootstrap', guiDomain(uid()), def.plistPath]);
    return { action: 'start', ok: true };
  } catch (err) {
    return { action: 'start', ok: false, error: String(err) };
  }
}

/** Stop (bootout) the listener. No-op if already stopped. Returns at next login via RunAtLoad. */
export function stopListener(def: ListenerDef): LifecycleResult {
  if (!isRunning(def.launchdLabel)) return { action: 'stop', ok: true, noop: true };
  try {
    run(['bootout', guiDomainTarget(uid(), def.launchdLabel)]);
    return { action: 'stop', ok: true };
  } catch (err) {
    return { action: 'stop', ok: false, error: String(err) };
  }
}

/** Restart: kickstart -k if running, else bootstrap. */
export function restartListener(def: ListenerDef): LifecycleResult {
  try {
    if (isRunning(def.launchdLabel)) {
      run(['kickstart', '-k', guiDomainTarget(uid(), def.launchdLabel)]);
    } else {
      run(['bootstrap', guiDomain(uid()), def.plistPath]);
    }
    return { action: 'restart', ok: true };
  } catch (err) {
    return { action: 'restart', ok: false, error: String(err) };
  }
}
