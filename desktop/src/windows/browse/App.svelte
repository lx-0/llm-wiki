<script lang="ts">
  import { onMount } from 'svelte';
  import { fmtAgo } from '../../lib/time';
  import TypeBadge from '../../ui/TypeBadge.svelte';
  import { typeToken } from '../../ui/types';
  import { capRows, type Entry, filterEntries, typeChips, typeCounts } from './filter';

  let all = $state<Entry[]>([]);
  let query = $state('');
  let type = $state('');
  let loaded = $state(false);

  const filtered = $derived(filterEntries(all, query, type));
  const { shown, hidden } = $derived(capRows(filtered));
  const chips = $derived(typeChips(all));
  const counts = $derived(typeCounts(filtered));

  onMount(async () => {
    all = (await window.vault.list()) as Entry[];
    loaded = true;
  });
</script>

<main class="browse">
  <header class="head">
    <input
      class="search"
      type="search"
      placeholder="Filter notes by title…"
      autocomplete="off"
      spellcheck="false"
      bind:value={query}
    />
    <span class="count num">{filtered.length}</span>
  </header>

  {#if chips.length > 1}
    <nav class="chips" aria-label="Filter by type">
      <button class="chip" class:on={type === ''} onclick={() => (type = '')}>All</button>
      {#each chips as kind}
        <button class="chip" class:on={type === kind} onclick={() => (type = kind)}>{kind}</button>
      {/each}
    </nav>
  {/if}

  <div class="list">
    {#each shown as entry (entry.file)}
      <button class="entry" style="--c: var({typeToken(entry.type)})" onclick={() => window.vault.openFile(entry.file)}>
        <TypeBadge kind={entry.type} />
        <span class="title">{entry.title}</span>
        <span class="ago num">{fmtAgo(entry.mtimeMs)}</span>
      </button>
    {/each}
    {#if hidden > 0}
      <p class="more">{hidden.toLocaleString()} more — narrow the search to see them.</p>
    {/if}
    {#if loaded && filtered.length === 0}
      <p class="empty">{all.length === 0 ? 'No notes yet — add material and update your library.' : 'Nothing matches.'}</p>
    {/if}
  </div>

  {#if counts.length > 0}
    <footer class="foot num">
      <span class="total">{filtered.length} {filtered.length === 1 ? 'note' : 'notes'}</span>
      {#each counts as { type: kind, count }}
        <span class="kind"><span class="dot" style="background: var({typeToken(kind)})"></span>{kind} {count}</span>
      {/each}
    </footer>
  {/if}
</main>

<style>
  .browse {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-4) var(--space-2);
  }
  .search {
    flex: 1;
    height: 32px;
    padding: 0 var(--space-3);
    border: 1px solid var(--line);
    border-radius: var(--radius-s);
    background: var(--bg-elevated);
    color: var(--text);
    font-size: var(--fs-l);
    outline: none;
  }
  .search::placeholder {
    color: var(--text-faint);
  }
  .search:focus-visible {
    border-color: var(--accent);
    box-shadow: var(--focus);
  }
  .count {
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    padding: 0 var(--space-4) var(--space-2);
  }
  .chip {
    height: var(--control-h-s);
    padding: 0 var(--space-3);
    border: 1px solid transparent;
    border-radius: 12px;
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-size: var(--fs-s);
    font-weight: 500;
    text-transform: capitalize;
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .chip:hover {
    background: var(--bg-hover);
    color: var(--text);
  }
  .chip.on {
    background: var(--accent);
    color: var(--text-on-accent);
  }
  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0 var(--space-2) var(--space-3);
  }
  .entry {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .entry:hover {
    background: var(--bg-hover);
  }
  .title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ago {
    color: var(--text-faint);
    font-size: var(--fs-s);
    flex: none;
  }
  .more,
  .empty {
    padding: var(--space-3);
    color: var(--text-muted);
    font-size: var(--fs-s);
    text-align: center;
  }
  .foot {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-4);
    border-top: 1px solid var(--line);
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .total {
    color: var(--text);
    font-weight: 500;
  }
  .kind {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    text-transform: capitalize;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
</style>
