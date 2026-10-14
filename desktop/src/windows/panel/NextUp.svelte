<script lang="ts">
  import { withRunState } from '../../lib/actions';
  import Button from '../../ui/Button.svelte';
  import { nextUp } from './sections';
  import { actions, busy, panel, runAction } from './store.svelte';

  const rows = $derived(withRunState(nextUp(actions()), panel.run.key, panel.run.results));
  const progressText = $derived(
    panel.run.progress?.total ? `${panel.run.progress.current} of ${panel.run.progress.total}` : '',
  );
  const progressPct = $derived(
    panel.run.progress?.total ? Math.round((panel.run.progress.current / panel.run.progress.total) * 100) : 0,
  );
</script>

<section class="next" aria-label="Next up">
  <h2 class="caps">Next up</h2>
  {#if !panel.loaded}
    <p class="empty">…</p>
  {:else if rows.length === 0}
    <p class="empty">Nothing to do — your wiki is current.</p>
  {:else}
    <div class="card">
      {#each rows as row (row.key)}
        <div class="row item">
          {#if row.severity}
            <span class="sev {row.severity}" role="img" aria-label={row.severity}></span>
          {:else}
            <span class="sev" aria-hidden="true"></span>
          {/if}
          <span class="title">{row.title}</span>
          {#if row.state === 'running'}
            <span class="progress num" aria-live="polite">
              <span class="bar" class:indeterminate={!panel.run.progress?.total}><span class="fill" style="width: {panel.run.progress?.total ? progressPct : 40}%"></span></span>
              {#if progressText}<span>{progressText}</span>{/if}
            </span>
          {:else if row.state === 'done'}
            <span class="pill ok">done</span>
          {:else if row.state === 'failed'}
            <span class="pill failed">failed</span>
          {:else}
            <Button size="s" disabled={busy()} onclick={() => void runAction(row.argv)}>{row.verb}</Button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .next {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .empty {
    padding: var(--space-1) 0;
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .item {
    min-height: 32px;
    padding-top: 4px;
    padding-bottom: 4px;
  }
  /* the dot column is always there so titles line up; it only lights up for probe findings */
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
  .title {
    flex: 1;
    min-width: 0;
  }
  .progress {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    width: 120px;
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
  .fill {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width var(--dur-normal) var(--ease-out);
  }
  .indeterminate .fill {
    animation: slide 1.2s var(--ease-out) infinite;
  }
  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(260%);
    }
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
</style>
