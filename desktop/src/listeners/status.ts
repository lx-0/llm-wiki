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
  return {
    id: args.id,
    running: args.running,
    channels: { mic, system },
    zombieSuspected,
    checkedAtMs: args.nowMs,
  };
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

// ---- capture timeline: hourly chunk counts (the Overview's heat strip) ---------

export interface CaptureTimeline {
  /** epoch ms of the first bin's start — a local hour boundary */
  startMs: number;
  bucketMs: number;
  /** chunks per bin, oldest first; the last bin is the current hour */
  mic: number[];
  system: number[];
}

const HOUR_MS = 3_600_000;

/** Start of the local hour containing `ms` — bins follow the operator's clock, not UTC. Bins
 *  are a fixed hour apart, so across a DST switch inside the window the labels drift by one
 *  hour for that day; a 24 h strip wears that twice a year. */
function hourStart(ms: number): number {
  const d = new Date(ms);
  d.setMinutes(0, 0, 0);
  return d.getTime();
}

/** Count samples into `hours` hourly bins ending with the current hour. Anything outside the
 *  window — older than the first bin or past the current hour — is dropped. */
export function bucketByHour(
  timesMs: readonly number[],
  nowMs: number,
  hours: number,
): { startMs: number; bucketMs: number; counts: number[] } {
  const bins = Math.max(1, Math.floor(hours));
  const startMs = hourStart(nowMs) - (bins - 1) * HOUR_MS;
  const counts = new Array<number>(bins).fill(0);
  for (const t of timesMs) {
    const index = Math.floor((t - startMs) / HOUR_MS);
    if (index >= 0 && index < bins) counts[index] += 1;
  }
  return { startMs, bucketMs: HOUR_MS, counts };
}

/** Epoch ms of every `audio_chunks` row matching `likePattern` since `sinceMs` — the same
 *  julianday trick as lastChunkMs, so the stored text format never matters. */
export function chunkTimesMs(dbPath: string, likePattern: string, sinceMs: number): number[] {
  const since = new Date(sinceMs).toISOString();
  const sql =
    `select cast((julianday(timestamp) - 2440587.5) * 86400000 as integer) ` +
    `from audio_chunks where file_path like '${likePattern.replace(/'/g, "''")}' ` +
    `and julianday(timestamp) >= julianday('${since}');`;
  try {
    const out = execFileSync('sqlite3', ['-readonly', dbPath, sql], { encoding: 'utf8' });
    return out
      .split('\n')
      .map(Number)
      .filter((ms) => Number.isFinite(ms) && ms > 0);
  } catch {
    return []; // db missing / unreadable ⇒ an empty timeline, never a crash
  }
}

/** Hourly mic / system chunk counts over the last `hours`, newest bin last. */
export function getCaptureTimeline(
  def: ListenerDef,
  hours = 24,
  nowMs: number = Date.now(),
): CaptureTimeline {
  const bins = Math.max(1, Math.floor(hours));
  const startMs = hourStart(nowMs) - (bins - 1) * HOUR_MS;
  const mic = bucketByHour(chunkTimesMs(def.dbPath, def.channels.mic, startMs), nowMs, bins);
  const system = bucketByHour(chunkTimesMs(def.dbPath, def.channels.system, startMs), nowMs, bins);
  return { startMs: mic.startMs, bucketMs: mic.bucketMs, mic: mic.counts, system: system.counts };
}
