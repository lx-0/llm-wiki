<script lang="ts">
  // Horizontal single-hue bars: the type badge is the row's identity, the bar its magnitude,
  // the value sits at the tip in text ink — every value labelled, so no axis. Rows are
  // keyboard-reachable; the tooltip repeats the row.
  import TypeBadge from './TypeBadge.svelte';
  import { tip } from './tip';

  interface Row {
    type: string;
    count: number;
    share: number;
  }

  interface Props {
    rows: Row[];
    unit: [string, string];
    label: string;
  }

  let { rows, unit, label }: Props = $props();
  const max = $derived(Math.max(1, ...rows.map((r) => r.count)));
  const fmt = (n: number): string => `${n.toLocaleString()} ${n === 1 ? unit[0] : unit[1]}`;
</script>

<div class="hbars" role="group" aria-label={label}>
  {#each rows as row (row.type)}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -- a data row is keyboard-reachable on purpose: its tooltip is the value -->
    <div class="bar-row" tabindex="0" use:tip={`${row.type} · ${fmt(row.count)} · ${row.share} %`}>
      <span class="key"><TypeBadge kind={row.type} /></span>
      <span class="track"><span class="fill" style="width: {Math.round((row.count / max) * 100)}%"></span></span>
      <span class="val num">{row.count.toLocaleString()}</span>
    </div>
  {/each}
</div>

<style>
  .hbars {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 76px minmax(0, 1fr) 40px;
    align-items: center;
    gap: var(--space-2);
    height: 20px;
    border-radius: var(--radius-s);
    outline: none;
  }
  .bar-row:focus-visible {
    box-shadow: var(--focus);
  }
  .key {
    display: inline-flex;
  }
  .track {
    display: block;
    height: 12px;
  }
  .fill {
    display: block;
    height: 100%;
    min-width: 2px;
    border-radius: 0 4px 4px 0;
    background: var(--accent);
    transition:
      width var(--dur-normal) var(--ease-out),
      background-color var(--dur-fast) var(--ease-out);
  }
  .bar-row:hover .fill,
  .bar-row:focus-visible .fill {
    background: color-mix(in oklch, var(--accent) 72%, var(--bg));
  }
  .val {
    font-size: var(--fs-s);
    text-align: right;
  }
</style>
