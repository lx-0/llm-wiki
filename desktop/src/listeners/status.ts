// Canonical listener-status logic — SINGLE SOURCE OF TRUTH for S02 (toggle state)
// and S03 (health window). Listener status is SYSTEM data (launchd + the listener's
// sqlite), NOT wiki-engine data, so it is read directly here — no Python `wiki`
// command in the loop (see M029-CONTEXT 2026-06-22 DRY re-scope).
//
// Split: pure derivation (no I/O, fully unit-tested) + a thin I/O wrapper.

import { execFileSync } from 'node:child_process';
import type { ListenerDef } from './registry';

/** A channel is "fresh" if its last chunk is within this many seconds.
 *  Chunks land ~every 30 s, so 120 s = ~4 missed chunks = clearly stale. */
export const FRESH_SEC = 120;
/** System-audio-zombie heuristic (mirrors ~/.screenpipe/watchdog.sh): listener
 *  running + mic fresh + system silent this long ⇒ the output stream died on wake. */
export const ZOMBIE_SYS_STALE_SEC = 1200;
export const ZOMBIE_MIC_FRESH_SEC = 600;

export interface ChannelStatus {
  /** epoch ms of the newest chunk, or null if none */
  lastCaptureAtMs: number | null;
  /** seconds since the newest chunk, or null if none */
  ageSeconds: number | null;
  fresh: boolean;
}

export interface ListenerStatus {
  id: string;
  /** launchd-registered (loaded) — not necessarily healthy */
  running: boolean;
  channels: { mic: ChannelStatus; system: ChannelStatus };
  /** running + mic fresh + system stale/absent ⇒ the known sleep/wake zombie */
  zombieSuspected: boolean;
  checkedAtMs: number;
}

// ---- pure derivation (no I/O) ----------------------------------------------

export function channelStatus(lastCaptureAtMs: number | null, nowMs: number): ChannelStatus {
  if (lastCaptureAtMs == null) return { lastCaptureAtMs: null, ageSeconds: null, fresh: false };
  const ageSeconds = Math.max(0, Math.round((nowMs - lastCaptureAtMs) / 1000));
  return { lastCaptureAtMs, ageSeconds, fresh: ageSeconds <= FRESH_SEC };
}

export function deriveStatus(args: {
  id: string;
  running: boolean;
  micLastMs: number | null;
  sysLastMs: number | null;
  nowMs: number;
}): ListenerStatus {
  const mic = channelStatus(args.micLastMs, args.nowMs);
  const system = channelStatus(args.sysLastMs, args.nowMs);
  const micFreshEnough = mic.ageSeconds != null && mic.ageSeconds <= ZOMBIE_MIC_FRESH_SEC;
  const sysStale = system.ageSeconds == null || system.ageSeconds >= ZOMBIE_SYS_STALE_SEC;
  const zombieSuspected = args.running && micFreshEnough && sysStale;
  return { id: args.id, running: args.running, channels: { mic, system }, zombieSuspected, checkedAtMs: args.nowMs };
}

// ---- thin I/O wrapper -------------------------------------------------------

/** launchd running-state: `launchctl list <label>` exits 0 iff the job is loaded. */
export function isRunning(launchdLabel: string): boolean {
  try {
    execFileSync('launchctl', ['list', launchdLabel], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

/** Newest `audio_chunks` timestamp matching `likePattern`, as epoch ms (null if none).
 *  Uses `sqlite3 -readonly` (safe alongside the WAL writer) and computes epoch ms via
 *  julianday so it is robust to the stored timestamp's text format. */
export function lastChunkMs(dbPath: string, likePattern: string): number | null {
  const sql =
    `select cast((julianday(max(timestamp)) - 2440587.5) * 86400000 as integer) ` +
    `from audio_chunks where file_path like '${likePattern.replace(/'/g, "''")}';`;
  try {
    const out = execFileSync('sqlite3', ['-readonly', dbPath, sql], { encoding: 'utf8' }).trim();
    if (!out) return null;
    const ms = Number(out);
    return Number.isFinite(ms) ? ms : null;
  } catch {
    return null; // db missing / unreadable ⇒ treat as no data
  }
}

/** Live status for one listener (hits launchctl + sqlite). nowMs injectable for tests. */
export function getListenerStatus(def: ListenerDef, nowMs: number = Date.now()): ListenerStatus {
  return deriveStatus({
    id: def.id,
    running: isRunning(def.launchdLabel),
    micLastMs: lastChunkMs(def.dbPath, def.channels.mic),
    sysLastMs: lastChunkMs(def.dbPath, def.channels.system),
    nowMs,
  });
}
