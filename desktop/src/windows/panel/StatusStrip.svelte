<script lang="ts">
  import { activity, countPerDay } from '../../lib/activity';
  import { fmtAgo } from '../../lib/time';
  import Button from '../../ui/Button.svelte';
  import Ring from '../../ui/Ring.svelte';
  import Sparkline from '../../ui/Sparkline.svelte';
  import { captureSummary, healthSummary } from './status';
  import { busy, panel, runAction, startCompile, toggleListener } from './store.svelte';

  type Tile = 'library' | 'health';
  let open = $state<Tile | null>(null);
  const toggle = (tile: Tile) => (open = open === tile ? null : tile);

  const now = $derived(panel.loaded ? Date.now() : 0);
  const adds = $derived(countPerDay(panel.entries, now));
  const act = $derived(activity(panel.entries, now));
  const health = $derived(healthSummary(panel.doctor));
  const listener = $derived(panel.listeners[0] ?? null);
  const capture = $derived(captureSummary(listener, panel.toggling));
  const recording = $derived(capture.state === 'recording');
  const toggling = $derived(listener ? panel.toggling.has(listener.id) : false);
  const compileLine = $derived.by(() => {
    if (panel.compile.running) {
      const { current, total } = panel.compile.progress;
      return total > 0 ? `Updating · ${current} of ${total}` : 'Updating…';
    }
    const r = panel.compile.result;
    if (!r) return null;
    return r.ok ? `Up to date · took ${Math.max(1, Math.round(r.durationMs / 60000))}m` : 'Update failed';
  });
  const runKey = (argv: string[] | undefined) => (argv ?? []).join(' ');
  const dispatchable = (check: { dispatchArgs?: string[] }, key: string): boolean =>
    Boolean(check.dispatchArgs?.length) && !/auth/.test(key);
</script>

<section class="strip" aria-label="Status">
  <div class="tiles">
    <button class="tile" class:open={open === 'library'} onclick={() => toggle('library')} aria-expanded={open === 'library'}>
      {#if panel.vault && !panel.vault.accessible}
        <span class="big warn">Can't read</span>
        <span class="cap">library</span>
      {:else}
        <span class="big num">{panel.vault ? panel.vault.articleCount.toLocaleString() : '—'}</span>
        <Sparkline values={adds} width={92} height={22} label="Notes updated per day, last 14 days" />
        <span class="cap num">{act.today > 0 ? `+${act.today} today` : 'notes'}</span>
      {/if}
    </button>

    <button class="tile" class:open={open === 'health'} onclick={() => toggle('health')} aria-expanded={open === 'health'}>
      <Ring level={health.level} value={health.level === 'ok' ? 'OK' : health.level === 'unknown' ? '…' : String(health.count)} size={38} />
      <span class="cap" class:warn={health.level === 'warn'} class:danger={health.level === 'critical'}>
        {health.level === 'ok' ? 'healthy' : health.level === 'unknown' ? 'health' : health.word}
      </span>
    </button>

    <!-- The capture tile IS the control: the universal red dot while recording, and the
         Pause / Resume button always in view — never a green "all good" for a live mic. -->
    <div class="tile capture">
      <span class="state" class:danger={capture.state === 'check'}>
        <span class="rec" class:on={recording} class:warn={capture.state === 'check'} aria-hidden="true"></span>{capture.word}
      </span>
      <span class="cap">{capture.state === 'check' ? 'system audio stalled' : capture.state === 'none' ? 'screen & audio' : 'screen, mic & system audio'}</span>
      {#if listener}
        <Button size="s" variant={listener.running ? 'secondary' : 'primary'} disabled={toggling} onclick={() => void toggleListener(listener.id, listener.running ? 'stop' : 'start')}>
          {listener.running ? 'Pause' : 'Resume'}
        </Button>
      {/if}
    </div>
  </div>

  {#if open === 'library'}
    <div class="detail card">
      {#if panel.vault && !panel.vault.accessible}
        <div class="row"><span class="grow">Grant Full Disk Access to read your library</span><Button size="s" onclick={() => window.vault.openFullDiskAccess()}>Open System Settings</Button></div>
      {:else}
        <div class="row">
          <span class="grow num">+{act.week} this week{panel.vault?.lastActivityMs ? ` · updated ${fmtAgo(panel.vault.lastActivityMs)}` : ''}</span>
          <Button size="s" variant="primary" disabled={busy()} onclick={() => void startCompile()}>Update knowledge</Button>
        </div>
        {#if compileLine}
          <div class="row sub" class:failed={panel.compile.result && !panel.compile.result.ok}>
            {#if panel.compile.running}
              <span class="bar" class:indeterminate={panel.compile.progress.total === 0}><span class="fill" style="width: {panel.compile.progress.total ? Math.round((panel.compile.progress.current / panel.compile.progress.total) * 100) : 100}%"></span></span>
            {/if}
            <span class="num">{compileLine}</span>
          </div>
        {/if}
      {/if}
    </div>
  {:else if open === 'health'}
    <div class="detail card">
      {#if !panel.doctor}
        <div class="row"><span class="grow muted">Health not checked yet</span></div>
      {:else if panel.doctor.checks.length === 0 && !panel.doctor.updateAvailable}
        <div class="row"><span class="grow">Everything healthy</span></div>
      {/if}
      {#each panel.doctor?.checks ?? [] as check (check.id)}
        {@const key = runKey(check.dispatchArgs)}
        <div class="row">
          <span class="sev {check.severity}"></span>
          <span class="grow">
            <span title={check.message}>{check.title}</span>
            {#if !dispatchable(check, key) && check.fix}
              <span class="sub-line">{check.fix}</span>
            {/if}
          </span>
          {#if dispatchable(check, key)}
            {#if panel.run.key === key}
              <span class="muted num">{panel.run.progress?.total ? `${panel.run.progress.current} of ${panel.run.progress.total}` : '…'}</span>
            {:else if panel.run.results.has(key)}
              <span class="pill" class:ok={panel.run.results.get(key)} class:danger={!panel.run.results.get(key)}>{panel.run.results.get(key) ? 'done' : 'failed'}</span>
            {:else}
              <Button size="s" disabled={busy()} onclick={() => void runAction(check.dispatchArgs ?? [])}>{check.verb ?? 'Fix'}</Button>
            {/if}
          {/if}
        </div>
      {/each}
      {#if panel.doctor?.updateAvailable}
        <div class="row">
          <span class="grow">App update available</span>
          <Button size="s" disabled={busy()} onclick={() => void runAction(['update'])}>Update app</Button>
        </div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .strip {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-2);
  }
  .tile {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 5px;
    height: 84px;
    padding: var(--space-2);
    border: 1px solid var(--line);
    border-radius: var(--radius-m);
    background: var(--bg-elevated);
    color: var(--text);
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  button.tile:hover {
    background: var(--bg-hover);
  }
  .tile.open {
    border-color: var(--accent);
  }
  .capture {
    gap: 3px;
  }
  .big {
    font-size: var(--fs-xl);
    font-weight: 600;
    line-height: 1;
  }
  .cap {
    font-size: var(--fs-xs);
    color: var(--text-muted);
    text-align: center;
  }
  .state {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: var(--fs-s);
    font-weight: 600;
  }
  .rec {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 1.5px solid var(--text-faint);
    background: transparent;
  }
  .rec.on {
    border-color: var(--danger);
    background: var(--danger);
  }
  .rec.warn {
    border-color: var(--warn);
    background: var(--warn);
  }
  .warn {
    color: var(--warn);
  }
  .danger {
    color: var(--danger);
  }
  .muted {
    color: var(--text-muted);
  }
  .detail .row {
    min-height: 36px;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .sub {
    font-size: var(--fs-s);
    color: var(--text-muted);
    gap: var(--space-2);
  }
  .sub.failed {
    color: var(--danger);
  }
  .sub-line {
    display: block;
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
  .bar {
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: var(--line);
    overflow: hidden;
  }
  .bar .fill {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width var(--dur-normal) var(--ease-out);
  }
  .bar.indeterminate .fill {
    animation: slide 1.2s var(--ease-out) infinite;
    width: 40% !important;
  }
  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(260%);
    }
  }
  .sev {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
    background: var(--warn);
  }
  .sev.critical {
    background: var(--danger);
  }
  .pill {
    font-size: var(--fs-xs);
    font-weight: 600;
    padding: 2px var(--space-2);
    border-radius: var(--radius-s);
    background: var(--ok-soft);
  }
  .pill.danger {
    background: var(--danger-soft);
  }
</style>
