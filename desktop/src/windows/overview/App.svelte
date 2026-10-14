<script lang="ts">
  import { onMount } from 'svelte';
  import { countPerDay } from '../../lib/activity';
  import Button from '../../ui/Button.svelte';
  import Columns from '../../ui/Columns.svelte';
  import { icon } from '../../ui/icons';
  import { columnScale, dayAxis, statTiles } from './charts';

  type VaultStatus = Awaited<ReturnType<typeof window.vault.status>>;
  type Entry = Awaited<ReturnType<typeof window.vault.list>>[number];
  type Doctor = Awaited<ReturnType<typeof window.vault.doctor>>;

  const DAYS = 30;

  let status = $state<VaultStatus>(null);
  let entries = $state<Entry[]>([]);
  let doctor = $state<Doctor>(null);
  let inbox = $state(0);
  let loaded = $state(false);
  let now = $state(0);

  const blocked = $derived(status !== null && !status.accessible);
  const perDay = $derived(countPerDay(entries, now, DAYS));
  const axis = $derived(dayAxis(now, DAYS));
  const scale = $derived(columnScale(perDay));
  const tiles = $derived(statTiles({ entries, inbox, issues: doctor?.checks.length ?? 0, now }));

  onMount(async () => {
    [status, entries, doctor, inbox] = await Promise.all([
      window.vault.status().catch(() => null),
      window.vault.list().catch(() => [] as Entry[]),
      window.vault.doctor().catch(() => null),
      window.vault
        .triage(false)
        .then((records) => records.length)
        .catch(() => 0),
    ]);
    now = Date.now();
    loaded = true;
  });
</script>

<main class="overview">
  <header class="head">
    <span class="logo">{@html icon.logo(18)}</span>
    <h1>Overview</h1>
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
          <Columns
            values={perDay}
            names={axis.days.map((d) => d.name)}
            ticks={axis.ticks}
            max={scale.max}
            yTicks={scale.ticks}
            unit={['note', 'notes']}
            label="Notes updated per day, last {DAYS} days"
          />
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
    gap: var(--space-2);
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
  }
  .chart {
    margin: 0;
    padding: var(--space-3) var(--space-4) var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
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
</style>
