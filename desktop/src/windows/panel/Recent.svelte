<script lang="ts">
  import { fmtAgo } from '../../lib/time';
  import { tip } from '../../ui/tip';
  import TypeBadge from '../../ui/TypeBadge.svelte';
  import { isNew } from './sections';
  import { panel } from './store.svelte';

  const recent = $derived(panel.vault?.recent ?? []);
</script>

{#if recent.length > 0}
  <section class="recent" aria-label="Recent entries">
    <h2 class="caps">Recent</h2>
    <div class="card">
      {#each recent as entry (entry.file)}
        <button class="entry" title="Open in Obsidian" onclick={() => window.vault.openFile(entry.file)}>
          {#if isNew(entry, panel.recentSeenMs)}
            <span class="dot new" role="img" use:tip={'New since you last looked'}></span>
          {:else}
            <span class="dot" aria-hidden="true"></span>
          {/if}
          <TypeBadge kind={entry.type} />
          <span class="title">{entry.title}</span>
          <span class="ago num">{fmtAgo(entry.mtimeMs)}</span>
        </button>
      {/each}
    </div>
  </section>
{/if}

<style>
  .recent {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .entry {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: 28px;
    padding: 3px var(--space-3);
    border: none;
    background: transparent;
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .entry + .entry {
    border-top: 1px solid var(--line);
  }
  .entry:hover {
    background: var(--bg-hover);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex: none;
    background: transparent;
  }
  .dot.new {
    background: var(--accent);
  }
  .title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ago {
    flex: none;
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
</style>
