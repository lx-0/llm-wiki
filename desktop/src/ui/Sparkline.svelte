<script lang="ts">
  // Thin bar sparkline: one bar per value, 2 px gaps, rounded data-ends on the baseline, the
  // last value (today) in full accent, the rest muted. Single series → no legend.
  interface Props {
    values: number[];
    width?: number;
    height?: number;
    label?: string;
  }

  let { values, width = 96, height = 28, label = '' }: Props = $props();

  const gap = 2;
  const barW = $derived(values.length ? (width - gap * (values.length - 1)) / values.length : 0);
  const max = $derived(Math.max(1, ...values));
  const bars = $derived(
    values.map((v, i) => {
      const h = v > 0 ? Math.max(2, (v / max) * height) : 1.5;
      return { x: i * (barW + gap), y: height - h, h, last: i === values.length - 1, zero: v === 0 };
    }),
  );
</script>

<svg class="spark" viewBox="0 0 {width} {height}" {width} {height} role="img" aria-label={label}>
  {#each bars as b}
    <rect x={b.x} y={b.y} width={barW} height={b.h} rx={Math.min(2, barW / 2)} class:last={b.last} class:zero={b.zero} />
  {/each}
</svg>

<style>
  .spark {
    display: block;
    overflow: visible;
  }
  rect {
    fill: var(--accent);
    opacity: 0.45;
  }
  rect.last {
    opacity: 1;
  }
  rect.zero {
    fill: var(--line-strong);
    opacity: 1;
  }
</style>
