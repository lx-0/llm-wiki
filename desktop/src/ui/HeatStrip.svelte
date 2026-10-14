<script lang="ts">
  // Rows × bins of 2 px-gapped cells in one hue at four lightness steps (--heat-1…4), the
  // --line track for "nothing"; hour ticks beneath and a scale legend. Every cell is a hit
  // target with a tooltip and keyboard focus.
  import { tip } from './tip';

  interface Row {
    label: string;
    counts: number[];
    /** 0 = nothing, 1…4 = quartile of a full hour */
    levels: number[];
  }

  interface Props {
    rows: Row[];
    /** per-bin names for the tooltip ("14:00–15:00") */
    names: string[];
    ticks: { index: number; label: string }[];
    unit: [string, string];
    label: string;
  }

  let { rows, names, ticks, unit, label }: Props = $props();

  let width = $state(0);
  const gutter = 48;
  const cellH = 14;
  const gap = 2;
  const band = 16;
  const bins = $derived(rows[0]?.counts.length ?? 0);
  const cellW = $derived(bins ? Math.max(1, (width - gutter - gap * (bins - 1)) / bins) : 0);
  const height = $derived(rows.length * (cellH + gap) - gap + band);
  const fmt = (n: number): string => `${n.toLocaleString()} ${n === 1 ? unit[0] : unit[1]}`;
</script>

<div class="strip" bind:clientWidth={width}>
  {#if width > 0 && bins > 0}
    <svg {width} {height} role="group" aria-label={label}>
      {#each rows as row, r (row.label)}
        <text class="key" x={gutter - 8} y={r * (cellH + gap) + cellH / 2} text-anchor="end" dominant-baseline="middle">{row.label}</text>
        {#each row.counts as count, i}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex -- a cell is keyboard-reachable on purpose: its tooltip is the value -->
          <rect
            class="cell l{row.levels[i]}"
            tabindex="0"
            x={gutter + i * (cellW + gap)}
            y={r * (cellH + gap)}
            width={cellW}
            height={cellH}
            rx="2"
            use:tip={`${row.label} · ${names[i] ?? ''} · ${fmt(count)}`}
          />
        {/each}
      {/each}
      {#each ticks as t}
        {#if t.index === bins - 1}
          <text class="tick" x={width} y={height - 2} text-anchor="end">{t.label}</text>
        {:else}
          <text class="tick" x={gutter + t.index * (cellW + gap) + cellW / 2} y={height - 2} text-anchor="middle">{t.label}</text>
        {/if}
      {/each}
    </svg>
    <div class="legend" aria-hidden="true">
      <span class="muted">none</span>
      <span class="sw l0"></span>
      <span class="sw l1"></span>
      <span class="sw l2"></span>
      <span class="sw l3"></span>
      <span class="sw l4"></span>
      <span class="muted">full hour</span>
    </div>
  {/if}
</div>

<style>
  .strip {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
  }
  .key,
  .tick {
    fill: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .cell {
    outline: none;
    transition: fill var(--dur-fast) var(--ease-out);
  }
  .cell:focus-visible {
    stroke: var(--accent);
    stroke-width: 2;
  }
  .cell.l0,
  .sw.l0 {
    fill: var(--line);
    background: var(--line);
  }
  .cell.l1,
  .sw.l1 {
    fill: var(--heat-1);
    background: var(--heat-1);
  }
  .cell.l2,
  .sw.l2 {
    fill: var(--heat-2);
    background: var(--heat-2);
  }
  .cell.l3,
  .sw.l3 {
    fill: var(--heat-3);
    background: var(--heat-3);
  }
  .cell.l4,
  .sw.l4 {
    fill: var(--heat-4);
    background: var(--heat-4);
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--fs-xs);
  }
  .sw {
    width: 14px;
    height: 10px;
    border-radius: 2px;
  }
  .muted {
    color: var(--text-muted);
  }
  .muted + .sw {
    margin-left: 2px;
  }
  .sw + .muted {
    margin-left: 2px;
  }
</style>
