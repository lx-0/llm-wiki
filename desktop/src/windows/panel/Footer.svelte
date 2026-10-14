<script lang="ts">
  import { cubicOut } from 'svelte/easing';
  import { prefersReducedMotion } from 'svelte/motion';
  import { scale } from 'svelte/transition';
  import { withRunState } from '../../lib/actions';
  import Button from '../../ui/Button.svelte';
  import { icon } from '../../ui/icons';
  import { configuredSources, toolRows } from './sections';
  import { actions, addLink, busy, loadCollectors, panel, resetAdd, runAction, syncAll } from './store.svelte';

  // Sources and Tools pop up over the content so the panel never grows past its clamp;
  // Add link takes the bar's own row. Nothing the footer opens changes the panel height.
  type Sheet = 'add' | 'sources' | 'tools';
  let sheet = $state<Sheet | null>(null);
  let url = $state('');
  let root = $state<HTMLElement | null>(null);

  function toggle(next: Sheet): void {
    sheet = sheet === next ? null : next;
    if (sheet === 'sources') void loadCollectors();
    if (sheet === 'add') queueMicrotask(() => document.getElementById('add-input')?.focus());
  }

  function close(): void {
    sheet = null;
    resetAdd();
  }

  const sources = $derived(configuredSources(panel.collectors ?? []));
  const tools = $derived(withRunState(toolRows(actions()), panel.run.key, panel.run.results));
  const syncKey = (name: string) => `collect ${name} --incremental`;
  const pop = $derived({ start: 0.96, duration: prefersReducedMotion.current ? 0 : 150, easing: cubicOut });

  async function submitLink(): Promise<void> {
    if (await addLink(url)) url = '';
  }
</script>

<svelte:window
  onpointerdown={(e) => {
    if ((sheet === 'sources' || sheet === 'tools') && root && !root.contains(e.target as Node)) sheet = null;
  }}
  onkeydown={(e) => {
    if (e.key === 'Escape' && sheet) close();
  }}
/>

<footer class="footer" bind:this={root}>
  {#if sheet === 'add'}
    <form class="bar" onsubmit={(e) => { e.preventDefault(); void submitLink(); }}>
      {#if panel.add.status === 'adding'}
        <span class="note grow">Adding link…</span>
      {:else if panel.add.status === 'done'}
        <span class="note ok grow">Added — it shows up after the next update</span>
      {:else if panel.add.status === 'failed'}
        <span class="note failed grow">Couldn't add that link</span>
        <Button size="s" onclick={() => resetAdd()}>Try again</Button>
      {:else if panel.add.status === 'invalid'}
        <span class="note failed grow">Not a web page or YouTube link</span>
        <Button size="s" onclick={() => resetAdd()}>Try again</Button>
      {:else}
        <input id="add-input" type="url" placeholder="Paste a web page or YouTube link" autocomplete="off" spellcheck="false" bind:value={url} />
        <Button size="s" variant="primary" type="submit" disabled={busy()}>Add</Button>
      {/if}
      <Button size="s" variant="quiet" title="Close" onclick={close}>{@html icon.close(13)}</Button>
    </form>
  {:else}
    <div class="bar">
      <button class="chip add" data-sheet="add" onclick={() => toggle('add')}>{@html icon.plus(13)} Save a web page</button>
      <button class="chip" data-sheet="sources" class:on={sheet === 'sources'} aria-expanded={sheet === 'sources'} onclick={() => toggle('sources')}>Sources</button>
      <button class="chip" data-sheet="tools" class:on={sheet === 'tools'} aria-expanded={sheet === 'tools'} onclick={() => toggle('tools')}>Tools</button>
      <span class="spacer"></span>
      <Button size="s" variant="quiet" onclick={() => window.app.quit()}>Quit</Button>
    </div>
  {/if}

  {#if sheet === 'sources'}
    <div class="sheet" data-layer aria-label="Sources" transition:scale={pop}>
      {#if panel.collectors === null}
        <div class="row"><span class="grow muted">…</span></div>
      {:else if sources.length === 0}
        <div class="row"><span class="grow muted">No sources configured</span></div>
      {:else}
        {#if sources.length > 1}
          <div class="row">
            <span class="grow">All sources <span class="muted num">· {sources.length}</span></span>
            <Button size="s" disabled={busy() || panel.syncQueue.length > 0} onclick={() => void syncAll()}>{panel.syncQueue.length > 0 ? '…' : 'Sync all'}</Button>
          </div>
        {/if}
        {#each sources as source (source.name)}
          {@const key = syncKey(source.name)}
          <div class="row">
            <span class="grow name">{source.name}</span>
            {#if panel.run.key === key}
              <span class="muted">…</span>
            {:else if panel.run.results.has(key)}
              <span class="note" class:ok={panel.run.results.get(key)} class:failed={!panel.run.results.get(key)}>{panel.run.results.get(key) ? 'synced' : 'failed'}</span>
            {:else}
              <Button size="s" disabled={busy()} onclick={() => void runAction(['collect', source.name, '--incremental'])}>Sync</Button>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {:else if sheet === 'tools'}
    <div class="sheet" data-layer aria-label="Tools" transition:scale={pop}>
      {#each tools as tool (tool.key)}
        <div class="row">
          <span class="grow">{tool.title}</span>
          {#if tool.state === 'running'}
            <span class="muted">…</span>
          {:else if tool.state === 'done' || tool.state === 'failed'}
            <span class="note" class:ok={tool.state === 'done'} class:failed={tool.state === 'failed'}>{tool.state}</span>
          {:else}
            <Button size="s" disabled={busy()} onclick={() => void runAction(tool.argv)}>{tool.verb}</Button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</footer>

<style>
  .footer {
    position: relative;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-height: var(--control-h-s);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    height: var(--control-h-s);
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--fs-s);
    font-weight: 500;
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .chip:hover,
  .chip.on {
    background: var(--bg-hover);
    color: var(--text);
  }
  /* the one daily action in the footer reads as a button, not as a footnote */
  .chip.add {
    border: 1px solid var(--line);
    background: var(--bg-sunken);
    color: var(--text);
  }
  .chip.add:hover {
    background: var(--bg-hover);
  }
  .spacer {
    flex: 1;
  }
  input {
    flex: 1;
    min-width: 0;
    height: var(--control-h-s);
    padding: 0 var(--space-2);
    border: 1px solid var(--line);
    border-radius: var(--radius-s);
    background: var(--bg-sunken);
    outline: none;
  }
  input::placeholder {
    color: var(--text-faint);
  }
  input:focus-visible {
    border-color: var(--accent);
    box-shadow: var(--focus);
  }

  /* the popover: opaque on purpose — it sits over the content, not in it */
  .sheet {
    position: absolute;
    left: 0;
    right: 0;
    bottom: calc(100% + var(--space-1));
    z-index: 20;
    max-height: 360px;
    overflow: auto;
    background: var(--bg);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-m);
    box-shadow:
      0 1px 2px oklch(0% 0 0 / 0.06),
      0 6px 16px oklch(0% 0 0 / 0.12),
      0 16px 40px oklch(0% 0 0 / 0.14);
    transform-origin: bottom left;
  }
  .sheet .row {
    min-height: 34px;
    padding-top: 4px;
    padding-bottom: 4px;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .name {
    text-transform: capitalize;
  }
  .muted {
    color: var(--text-muted);
  }
  .note {
    font-size: var(--fs-xs);
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .note.ok {
    color: var(--ok);
  }
  .note.failed {
    color: var(--danger);
  }
</style>
