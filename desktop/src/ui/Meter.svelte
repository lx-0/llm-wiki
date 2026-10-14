<script lang="ts">
  // Two thin horizontal level bars (0..1 each) with a label column — freshness meters.
  interface Props {
    rows: { label: string; level: number }[];
    tone?: 'ok' | 'warn' | 'muted';
  }

  let { rows, tone = 'ok' }: Props = $props();
</script>

<div class="meter {tone}">
  {#each rows as entry}
    <div class="line">
      <span class="label">{entry.label}</span>
      <span class="track"><span class="fill" style="width: {Math.round(Math.max(0, Math.min(1, entry.level)) * 100)}%"></span></span>
    </div>
  {/each}
</div>

<style>
  .meter {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
  }
  .line {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .label {
    width: 38px;
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
  .track {
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: var(--line);
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--ok);
    transition: width var(--dur-normal) var(--ease-out);
  }
  .warn .fill {
    background: var(--warn);
  }
  .muted .fill {
    background: var(--text-faint);
  }
</style>
