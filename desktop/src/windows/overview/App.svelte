<script lang="ts">
  import { onMount } from 'svelte';
  import { mergeActions, withRunState } from '../../lib/actions';
  import { countPerDay } from '../../lib/activity';
  import Button from '../../ui/Button.svelte';
  import Columns from '../../ui/Columns.svelte';
  import DataTable from '../../ui/DataTable.svelte';
  import HBars from '../../ui/HBars.svelte';
  import HeatStrip from '../../ui/HeatStrip.svelte';
  import { icon } from '../../ui/icons';
  import Ring from '../../ui/Ring.svelte';
  import { nextUp } from '../panel/sections';
  import { healthSummary } from '../panel/status';
  import { columnScale, dayAxis, heatLevel, hourName, hourTicks, statTiles, typeBars } from './charts';

  type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
  type Entry = Awaited<ReturnType<typeof window.vault.list>>[number];
  type Doctor = Awaited<ReturnType<typeof window.vault.doctor>>;
  type Menu = Awaited<ReturnType<typeof window.vault.menu>>;
  type Timeline = Awaited<ReturnType<typeof window.listeners.timeline>>;

  const DAYS = 30;
  const HOURS = 24;
  const LISTENER = 'screenpipe';
  const NEXT_UP_MAX = 8;

  let status = $state<VaultStatus>(null);
  let entries = $state<Entry[]>([]);
  let doctor = $state<Doctor>(null);
  let menu = $state<Menu>(null);
  let timeline = $state<Timeline>(null);
  let inbox = $state(0);
  let loaded = $state(false);
  let now = $state(0);
  let view = $state<'charts' | 'table'>('charts');
  /** the one engine command in flight (argv key) + results kept while the window is open */
  let run = $state({ key: null as string | null, results: new Map<string, boolean>() });

  const blocked = $derived(status !== null && !status.accessible);
  const table = $derived(view === 'table');
  const busy = $derived(run.key !== null);
  const perDay = $derived(countPerDay(entries, now, DAYS));
  const axis = $derived(dayAxis(now, DAYS));
  const scale = $derived(columnScale(perDay));
  const tiles = $derived(statTiles({ entries, inbox, issues: doctor?.checks.length ?? 0, now }));
  const types = $derived(typeBars(entries));
  const heat = $derived.by(() => {
    const t = timeline;
    if (!t) return null;
    const total = t.mic.reduce((a, b) => a + b, 0) + t.system.reduce((a, b) => a + b, 0);
    return {
      names: t.mic.map((_, i) => hourName(t.startMs, i)),
      ticks: hourTicks(t.startMs, t.mic.length),
      rows: [
        { label: 'mic', counts: t.mic, levels: t.mic.map((c) => heatLevel(c)) },
        { label: 'system', counts: t.system, levels: t.system.map((c) => heatLevel(c)) },
      ],
      total,
    };
  });
  const health = $derived(healthSummary(doctor));
  // Same order as the panel's Next up — critical first — so position carries urgency for a
  // reader who cannot tell the two dot colours apart.
  const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1 };
  const checks = $derived(
    [...(doctor?.checks ?? [])].sort((a, b) => (SEVERITY_RANK[a.severity] ?? 2) - (SEVERITY_RANK[b.severity] ?? 2)),
  );
  // Doctor rows live in the Health card above; Next up here is the engine's counted work only,
  // so nothing appears twice on one screen.
  const actions = $derived(
    withRunState(
      nextUp(mergeActions({ doctor: [], menu: menu?.suggestions ?? [], tools: menu?.tools ?? [] }), NEXT_UP_MAX),
      run.key,
      run.results,
    ),
  );
  const dispatchable = (check: { dispatchArgs?: string[] }, key: string): boolean =>
    Boolean(check.dispatchArgs?.length) && !/auth/.test(key);
  const runKey = (argv: string[] | undefined): string => (argv ?? []).join(' ');

  async function loadAll(): Promise<void> {
    [status, entries, doctor, menu, timeline, inbox] = await Promise.all([
      window.vault.status().catch(() => null),
      window.vault.list().catch(() => [] as Entry[]),
      window.vault.doctor().catch(() => null),
      window.vault.menu().catch(() => null),
      window.listeners.timeline(LISTENER, HOURS).catch(() => null),
      window.vault
        .triage(false)
        .then((records) => records.length)
        .catch(() => 0),
    ]);
    now = Date.now();
    loaded = true;
  }

  async function runAction(argv: string[]): Promise<void> {
    if (busy || argv.length === 0) return;
    const key = argv.join(' ');
    run.key = key;
    run.results.delete(key);
    run.results = new Map(run.results);
    const res = await window.vault.runArgs(argv);
    if (!res.started && !res.running) run.key = null;
  }

  onMount(() => {
    void loadAll();
    window.vault.onRunDone(({ id, result }) => {
      if (run.key === id) run.key = null;
      run.results.set(id, result.ok);
      run.results = new Map(run.results);
      void loadAll();
    });
  });
</script>

<main class="overview">
  <header class="head">
    <span class="logo">{@html icon.logo(18)}</span>
    <h1>Overview</h1>
    <div class="seg" role="group" aria-label="View">
      <button class="seg-btn" class:on={!table} aria-pressed={!table} data-view="charts" onclick={() => (view = 'charts')}>Charts</button>
      <button class="seg-btn" class:on={table} aria-pressed={table} data-view="table" onclick={() => (view = 'table')}>Table</button>
    </div>
    {#if status}
      <button class="vault" title="Open in Obsidian" onclick={() => void window.vault.openInObsidian()}>
        {status.name}{@html icon.external(11)}
      </button>
    {/if}
  </header>

  {#if blocked}
    <section class="card blocked">
      <span>Can't read your library — grant Full Disk Access to see it here.</span>
      <Button size="s" onclick={() => window.vault.openFullDiskAccess()}>Open System Settings</Button>
    </section>
  {:else}
    <section class="figures">
      <div class="hero">
        <span class="hero-value">{status ? status.articleCount.toLocaleString() : '—'}</span>
        <span class="hero-label">notes</span>
      </div>
      {#each tiles as tile (tile.label)}
        <div class="tile card">
          <span class="tile-label">{tile.label}</span>
          <span class="tile-value">{loaded ? tile.value : '—'}</span>
        </div>
      {/each}
    </section>

    <section class="charts">
      <figure class="card chart">
        <figcaption>
          <span class="title">Notes updated per day</span>
          <span class="sub">{entries.length === 0 && loaded ? 'no notes yet' : `last ${DAYS} days`}</span>
        </figcaption>
        {#if loaded}
          {#if table}
            <DataTable caption="Notes updated per day" columns={['Day', 'Notes']} rows={axis.days.map((d, i) => [d.name, perDay[i]])} />
          {:else}
            <Columns
              values={perDay}
              names={axis.days.map((d) => d.name)}
              ticks={axis.ticks}
              max={scale.max}
              yTicks={scale.ticks}
              unit={['note', 'notes']}
              height={130}
              label="Notes updated per day, last {DAYS} days"
            />
          {/if}
        {/if}
      </figure>

      <figure class="card chart">
        <figcaption>
          <span class="title">Notes by type</span>
          <span class="sub">{loaded && types.length === 0 ? 'no notes yet' : `${types.length} types`}</span>
        </figcaption>
        {#if loaded && types.length > 0}
          {#if table}
            <DataTable caption="Notes by type" columns={['Type', 'Notes', 'Share']} rows={types.map((t) => [t.type, t.count, `${t.share} %`])} />
          {:else}
            <HBars rows={types} unit={['note', 'notes']} label="Notes by type" />
          {/if}
        {/if}
      </figure>

      <figure class="card chart">
        <figcaption>
          <span class="title">Capture</span>
          <span class="sub">{heat ? (heat.total === 0 ? 'nothing in the last 24 h' : 'last 24 h') : loaded ? 'no capture process' : ''}</span>
        </figcaption>
        {#if heat}
          {#if table}
            <DataTable
              caption="Audio chunks per hour, last 24 h"
              columns={['Hour', 'Mic', 'System']}
              rows={heat.names.map((name, i) => [name, heat.rows[0].counts[i], heat.rows[1].counts[i]])}
            />
          {:else}
            <HeatStrip rows={heat.rows} names={heat.names} ticks={heat.ticks} unit={['chunk', 'chunks']} label="Audio chunks per hour, mic and system, last 24 h" />
          {/if}
        {/if}
      </figure>

      <figure class="card chart">
        <figcaption><span class="title">Health</span></figcaption>
        <div class="health">
          <div class="ring">
            <Ring level={health.level} value={health.level === 'ok' ? 'OK' : health.level === 'unknown' ? '…' : String(health.count)} size={44} />
            <span class="word" class:warn={health.level === 'warn'} class:danger={health.level === 'critical'}>
              {health.level === 'ok' ? 'healthy' : health.level === 'unknown' ? 'not checked' : health.word}
            </span>
          </div>
          <div class="rows">
            {#if doctor && doctor.checks.length === 0 && !doctor.updateAvailable}
              <div class="row"><span class="grow">Everything healthy</span></div>
            {/if}
            {#each checks as check (check.id)}
              {@const key = runKey(check.dispatchArgs)}
              <div class="row">
                <span class="sev {check.severity}" role="img" aria-label={check.severity}></span>
                <span class="grow">
                  <span title={check.message}>{check.title}</span>
                  {#if !dispatchable(check, key) && check.fix}
                    <span class="sub-line">{check.fix}</span>
                  {/if}
                </span>
                {#if dispatchable(check, key)}
                  {#if run.key === key}
                    <span class="muted">…</span>
                  {:else if run.results.has(key)}
                    <span class="pill" class:ok={run.results.get(key)} class:failed={!run.results.get(key)}>{run.results.get(key) ? 'done' : 'failed'}</span>
                  {:else}
                    <Button size="s" disabled={busy} onclick={() => void runAction(check.dispatchArgs ?? [])}>{check.verb ?? 'Fix'}</Button>
                  {/if}
                {/if}
              </div>
            {/each}
            {#if doctor?.updateAvailable}
              <div class="row">
                <span class="grow">App update available</span>
                <Button size="s" disabled={busy} onclick={() => void runAction(['update'])}>Update app</Button>
              </div>
            {/if}
          </div>
        </div>
      </figure>

      <figure class="card chart wide">
        <figcaption>
          <span class="title">Next up</span>
          {#if actions.length > 0}<span class="sub num">{actions.length}</span>{/if}
        </figcaption>
        {#if loaded && actions.length === 0}
          <p class="empty">Nothing to do — your wiki is current.</p>
        {:else}
          <div class="rows">
            {#each actions as row (row.key)}
              <div class="row">
                {#if row.severity}
                  <span class="sev {row.severity}" role="img" aria-label={row.severity}></span>
                {:else}
                  <span class="sev" aria-hidden="true"></span>
                {/if}
                <span class="grow">{row.title}</span>
                {#if row.state === 'running'}
                  <span class="muted">…</span>
                {:else if row.state === 'done' || row.state === 'failed'}
                  <span class="pill" class:ok={row.state === 'done'} class:failed={row.state === 'failed'}>{row.state}</span>
                {:else}
                  <Button size="s" disabled={busy} onclick={() => void runAction(row.argv)}>{row.verb}</Button>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </figure>
    </section>
  {/if}
</main>

<style>
  .overview {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-height: 100vh;
    padding: var(--space-4) var(--space-5) var(--space-5);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .logo {
    display: inline-flex;
    color: var(--text);
  }
  h1 {
    font-size: var(--fs-l);
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .seg {
    display: inline-flex;
    padding: 2px;
    border-radius: var(--radius-s);
    background: var(--bg-sunken);
  }
  .seg-btn {
    height: 22px;
    padding: 0 var(--space-3);
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-muted);
    font-size: var(--fs-s);
    font-weight: 500;
    transition:
      background-color var(--dur-fast) var(--ease-out),
      color var(--dur-fast) var(--ease-out);
  }
  .seg-btn.on {
    background: var(--bg-elevated);
    color: var(--text);
    box-shadow: 0 1px 2px oklch(0% 0 0 / 0.08);
  }
  .vault {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-left: auto;
    height: 22px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-size: var(--fs-xs);
    font-weight: 600;
    transition: color var(--dur-fast) var(--ease-out);
  }
  .vault:hover {
    color: var(--accent);
  }
  .blocked {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
  }

  .figures {
    display: grid;
    grid-template-columns: minmax(160px, 1.2fr) repeat(4, 1fr);
    gap: var(--space-3);
    align-items: stretch;
  }
  .hero {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
  }
  .hero-value {
    font-size: 48px;
    font-weight: 600;
    line-height: 1;
    letter-spacing: -0.02em;
  }
  .hero-label {
    color: var(--text-muted);
    font-size: var(--fs-m);
  }
  .tile {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
    padding: var(--space-3) var(--space-4);
  }
  .tile-label {
    font-size: var(--fs-s);
    color: var(--text-muted);
  }
  .tile-value {
    font-size: var(--fs-xl);
    font-weight: 600;
    line-height: 1.1;
  }

  .charts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
    align-items: stretch; /* cards in a row meet at the bottom */
  }
  .chart {
    margin: 0;
    padding: var(--space-3) var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }
  .wide {
    grid-column: 1 / -1;
  }
  figcaption {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .title {
    font-weight: 600;
  }
  .sub {
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
  .empty {
    color: var(--text-muted);
    font-size: var(--fs-s);
  }

  .health {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr);
    gap: var(--space-3);
    align-items: start;
  }
  .ring {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding-top: 2px;
  }
  .word {
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
  .word.warn {
    color: var(--warn);
  }
  .word.danger {
    color: var(--danger);
  }
  .rows {
    display: flex;
    flex-direction: column;
  }
  .rows .row {
    min-height: 34px;
    padding: 4px 0;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .muted {
    color: var(--text-muted);
  }
  .sev {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
    background: transparent;
  }
  .sev.warning {
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
  }
  .pill.ok {
    background: var(--ok-soft);
    color: var(--ok);
  }
  .pill.failed {
    background: var(--danger-soft);
    color: var(--danger);
  }
  .sub-line {
    display: block;
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
</style>
