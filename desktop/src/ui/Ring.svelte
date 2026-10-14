<script lang="ts">
  // Status ring: a thin track plus a full arc in the status colour, the value centred in text
  // ink — colour never carries the meaning alone (the caller adds the word).
  interface Props {
    level: 'ok' | 'warn' | 'critical' | 'unknown';
    value: string;
    size?: number;
  }

  let { level, value, size = 40 }: Props = $props();
  const stroke = 3;
  const r = $derived((size - stroke) / 2);
  const c = $derived(2 * Math.PI * r);
</script>

<svg class="ring {level}" viewBox="0 0 {size} {size}" width={size} height={size} aria-hidden="true">
  <circle class="track" cx={size / 2} cy={size / 2} {r} stroke-width={stroke} />
  <circle class="arc" cx={size / 2} cy={size / 2} {r} stroke-width={stroke} stroke-dasharray={c} stroke-dashoffset={level === 'unknown' ? c * 0.75 : 0} />
  <text x="50%" y="50%" class="value num">{value}</text>
</svg>

<style>
  .ring {
    display: block;
    transform: rotate(-90deg);
  }
  circle {
    fill: none;
    stroke-linecap: round;
  }
  .track {
    stroke: var(--line);
  }
  .arc {
    stroke: var(--text-faint);
    transition: stroke-dashoffset var(--dur-normal) var(--ease-out);
  }
  .ok .arc {
    stroke: var(--ok);
  }
  .warn .arc {
    stroke: var(--warn);
  }
  .critical .arc {
    stroke: var(--danger);
  }
  .value {
    transform: rotate(90deg);
    transform-origin: center;
    fill: var(--text);
    font-size: 12px;
    font-weight: 600;
    text-anchor: middle;
    dominant-baseline: central;
  }
</style>
