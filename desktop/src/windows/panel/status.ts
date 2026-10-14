// Status-strip derivations — pure functions over the panel store's data. Day-level activity
// counting lives in lib/activity.ts, shared with the Overview.

interface DoctorLike {
  checks: { severity: string }[];
}

interface ListenerLike {
  id: string;
  running: boolean;
  zombieSuspected: boolean;
  channels: { mic: ChannelLike; system: ChannelLike };
}

interface ChannelLike {
  ageSeconds: number | null;
  fresh: boolean;
}

/** Mirrors listeners/status.ts ZOMBIE_SYS_STALE_SEC — a channel is empty at this age. */
const STALE_SEC = 1200;

export type HealthLevel = 'ok' | 'warn' | 'critical' | 'unknown';

export function healthSummary(doctor: DoctorLike | null): {
  level: HealthLevel;
  count: number;
  word: string;
} {
  if (!doctor) return { level: 'unknown', count: 0, word: '—' };
  const count = doctor.checks.length;
  const critical = doctor.checks.some((c) => c.severity === 'critical');
  const level: HealthLevel = count === 0 ? 'ok' : critical ? 'critical' : 'warn';
  return { level, count, word: count === 0 ? 'OK' : count === 1 ? 'issue' : 'issues' };
}

export type CaptureState = 'recording' | 'paused' | 'check' | 'starting' | 'stopping' | 'none';

function level(channel: ChannelLike): number {
  if (channel.fresh) return 1;
  if (channel.ageSeconds == null) return 0;
  return Math.max(0, 1 - channel.ageSeconds / STALE_SEC);
}

export function captureSummary(
  listener: ListenerLike | null,
  toggling: ReadonlyMap<string, 'start' | 'stop'>,
): { state: CaptureState; word: string; mic: number; system: number } {
  if (!listener) return { state: 'none', word: 'Not configured', mic: 0, system: 0 };
  const mic = level(listener.channels.mic);
  const system = level(listener.channels.system);
  const pending = toggling.get(listener.id);
  if (pending === 'start') return { state: 'starting', word: 'Starting…', mic, system };
  if (pending === 'stop') return { state: 'stopping', word: 'Stopping…', mic, system };
  if (!listener.running) return { state: 'paused', word: 'Paused', mic, system };
  if (listener.zombieSuspected) return { state: 'check', word: 'Check', mic, system };
  return { state: 'recording', word: 'Recording', mic, system };
}
