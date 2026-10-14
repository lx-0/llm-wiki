<script lang="ts">
  // Single-series column chart on tokens: thin bars with a surface gap, rounded caps square at
  // the baseline, hairline gridlines at 0 and max, one direct label (today), and a tooltip
  // per bar — the whole slot is the hit target. One series → no legend; the caption names it.
  import { tip } from './tip';

  interface Props {
    values: number[];
    /** per-bar names for the tooltip ("Wed 14 Oct") */
    names: string[];
    ticks: { index: number; label: string }[];
    max: number;
    yTicks: number[];
    /** singular + plural unit for the tooltip value */
    unit: [string, string];
    height?: number;
    label: string;
  }

  let { values, names, ticks, max, yTicks, unit, height = 150, label }: Props = $props();

  let width = $state(0);
  const gutter = 28; // y tick labels
  const band = 18; // x labels
  const pad = 14; // room for the direct label above a full bar
  const plotTop = pad;
  const plotH = $derived(height - band - pad);
  const baseline = $derived(plotTop + plotH);
  const n = $derived(values.length);
  const slot = $derived(n ? (width - gutter) / n : 0);
  const barW = $derived(Math.max(1, Math.min(24, slot - 2)));
  const r = $derived(Math.min(4, barW / 2));
  const bars = $derived(
    values.map((v, i) => {
      const x = gutter + i * slot + (slot - barW) / 2;
      const h = max > 0 ? (v / max) * plotH : 0;
      return { v, i, x, y: baseline - h, h, hitX: gutter + i * slot, name: names[i] ?? '' };
    }),
  );
  const cap = (b: { x: number; y: number; h: number }): string =>
    b.h <= r
      ? `M${b.x},${baseline - b.h}H${b.x + barW}V${baseline}H${b.x}Z`
      : `M${b.x},${b.y + r}a${r},${r} 0 0 1 ${r},-${r}h${barW - 2 * r}a${r},${r} 0 0 1 ${r},${r}V${baseline}H${b.x}Z`;
  const fmt = (v: number): string => `${v.toLocaleString()} ${v === 1 ? unit[0] : unit[1]}`;
  const last = $derived(bars[bars.length - 1]);
</script>

<div class="chart" bind:clientWidth={width}>
  {#if width > 0 && n > 0}
    <svg {width} {height} role="img" aria-label={label}>
      {#each yTicks as t}
        {@const y = baseline - (max > 0 ? (t / max) * plotH : 0)}
        <line class="grid" x1={gutter} x2={width} y1={y} y2={y} />
        <text class="tick num" x={gutter - 6} {y} text-anchor="end" dominant-baseline="middle">{t.toLocaleString()}</text>
      {/each}
      {#each bars as b (b.i)}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -- a data point is keyboard-reachable on purpose: its tooltip is the value -->
        <g class="col" tabindex="0" use:tip={`${b.name} · ${fmt(b.v)}`}>
          <rect class="hit" x={b.hitX} y={plotTop} width={slot} height={plotH} />
          {#if b.h > 0}
            <path class="bar" d={cap(b)} />
          {/if}
        </g>
      {/each}
      {#each ticks as t}
        {#if t.index === n - 1}
          <text class="tick" x={width} y={height - 4} text-anchor="end">{t.label}</text>
        {:else}
          <text class="tick" x={gutter + t.index * slot + slot / 2} y={height - 4} text-anchor="middle">{t.label}</text>
        {/if}
      {/each}
      {#if last && last.v > 0}
        <text class="value num" x={last.x + barW / 2} y={last.y - 4} text-anchor="middle">{last.v.toLocaleString()}</text>
      {/if}
    </svg>
  {/if}
</div>

<style>
  .chart {
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
  }
  .grid {
    stroke: var(--line);
    stroke-width: 1;
  }
  .tick {
    fill: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .value {
    fill: var(--text);
    font-size: var(--fs-xs);
    font-weight: 600;
  }
  .hit {
    fill: transparent;
  }
  .bar {
    fill: var(--accent);
    transition: fill var(--dur-fast) var(--ease-out);
  }
  .col {
    outline: none;
  }
  .col:hover .bar,
  .col:focus-visible .bar {
    fill: color-mix(in oklch, var(--accent) 72%, var(--bg));
  }
  .col:focus-visible .hit {
    stroke: var(--accent);
    stroke-width: 2;
  }
</style>
