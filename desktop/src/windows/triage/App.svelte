<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../ui/Button.svelte';
  import Switch from '../../ui/Switch.svelte';
  import { type Group, groupRecords, metaLine, pendingCount, type TriageRecord } from './groups';

  type Action = 'accept' | 'dismiss';

  let records = $state<TriageRecord[]>([]);
  let showResolved = $state(false);
  let loaded = $state(false);
  let busy = $state(new Set<string>());
  let errors = $state(new Map<string, string>());
  let batching = $state(new Map<string, { done: number; total: number }>());

  const groups = $derived(groupRecords(records));
  const pending = $derived(pendingCount(records));

  async function load(): Promise<void> {
    records = await window.vault.triage(showResolved);
    loaded = true;
  }

  onMount(load);

  async function act(stem: string, action: Action): Promise<void> {
    if (busy.has(stem)) return;
    errors.delete(stem);
    busy.add(stem);
    busy = new Set(busy);
    const res = await window.vault.triageAction(stem, action);
    busy.delete(stem);
    busy = new Set(busy);
    if (res.ok) {
      await load();
    } else {
      errors.set(stem, res.message || 'That did not work — try again.');
      errors = new Map(errors);
    }
  }

  async function batch(group: Group, action: Action): Promise<void> {
    if (batching.has(group.key)) return;
    const stems = group.items.filter((r) => r.status === 'pending').map((r) => r.stem);
    if (stems.length === 0) return;
    const verb = action === 'accept' ? 'Keep' : 'Dismiss';
    if (!window.confirm(`${verb} all ${stems.length} ${group.label.toLowerCase()}?`)) return;
    batching.set(group.key, { done: 0, total: stems.length });
    batching = new Map(batching);
    let next = 0;
    const worker = async (): Promise<void> => {
      while (next < stems.length) {
        const stem = stems[next++];
        await window.vault.triageAction(stem, action);
        const progress = batching.get(group.key);
        if (progress) {
          progress.done += 1;
          batching = new Map(batching);
        }
      }
    };
    await Promise.all([worker(), worker(), worker()]); // small pool — gentle on uv spawns
    batching.delete(group.key);
    batching = new Map(batching);
    await load();
  }
</script>

<main class="triage">
  <header class="head">
    <h1>Inbox {#if pending}<span class="pill num">{pending}</span>{/if}</h1>
    <label class="toggle">
      <span>Show resolved</span>
      <Switch bind:checked={showResolved} label="Show resolved" onchange={() => void load()} />
    </label>
  </header>

  <div class="body">
    {#if loaded && groups.length === 0}
      <p class="empty">Nothing to sort — new captures land here.</p>
    {/if}

    {#each groups as group (group.key)}
      {@const progress = batching.get(group.key)}
      <section class="group" class:muted={group.key === 'note'}>
        <div class="group-head">
          <span class="group-label" style="--c: var(--type-{group.key === 'task' ? 'project' : group.key === 'idea' ? 'map' : group.key === 'note' ? 'concept' : 'note'})">
            <span class="dot"></span>{group.label} <span class="group-count num">{group.pending}</span>
          </span>
          {#if progress}
            <span class="progress num">{progress.done} of {progress.total}…</span>
          {:else if group.pending > 1}
            <span class="batch">
              <Button size="s" onclick={() => void batch(group, 'accept')}>Keep all</Button>
              <Button size="s" variant="quiet" onclick={() => void batch(group, 'dismiss')}>Dismiss all</Button>
            </span>
          {/if}
        </div>

        <div class="card">
          {#each group.items as r (r.stem)}
            <div class="row item" class:resolved={r.status !== 'pending'}>
              <div class="main">
                <div class="summary">{r.summary}</div>
                {#if r.source}
                  <button class="meta link" title="Open {r.source} in Obsidian" onclick={() => window.vault.openFile(r.source)}>{metaLine(r)}</button>
                {:else}
                  <div class="meta">{metaLine(r)}</div>
                {/if}
                {#if errors.get(r.stem)}
                  <div class="error">{errors.get(r.stem)}</div>
                {/if}
              </div>
              {#if r.status === 'pending'}
                {#if r.confidence === 'low'}
                  <span class="unsure" title={r.detail ? `Low confidence — ${r.detail}` : 'Low confidence — worth a look'}>unsure</span>
                {/if}
                {#if busy.has(r.stem) || progress}
                  <span class="working">…</span>
                {:else}
                  <span class="actions">
                    <Button size="s" onclick={() => void act(r.stem, 'accept')}>Keep</Button>
                    <Button size="s" variant="quiet" onclick={() => void act(r.stem, 'dismiss')}>Dismiss</Button>
                  </span>
                {/if}
              {/if}
            </div>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</main>

<style>
  .triage {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5) var(--space-3);
  }
  h1 {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--fs-xl);
    font-weight: 600;
  }
  .pill {
    height: 20px;
    padding: 0 var(--space-2);
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: var(--fs-s);
    font-weight: 600;
    display: inline-flex;
    align-items: center;
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .body {
    flex: 1;
    overflow-y: auto;
    padding: 0 var(--space-5) var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .empty {
    padding: var(--space-6) 0;
    text-align: center;
    color: var(--text-muted);
  }
  .group.muted {
    opacity: 0.85;
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }
  .group-label {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 600;
    color: var(--c);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c);
  }
  .group-count {
    color: var(--text-muted);
    font-weight: 500;
  }
  .batch,
  .actions {
    display: inline-flex;
    gap: var(--space-1);
    flex: none;
  }
  .progress {
    color: var(--text-muted);
    font-size: var(--fs-s);
  }
  .item {
    align-items: center;
  }
  .item.resolved {
    opacity: 0.5;
  }
  .main {
    flex: 1;
    min-width: 0;
  }
  .summary {
    font-weight: 500;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .meta {
    margin-top: 2px;
    font-size: var(--fs-s);
    color: var(--text-muted);
  }
  .meta.link {
    border: none;
    background: none;
    padding: 0;
    text-align: left;
  }
  .meta.link:hover {
    color: var(--accent);
  }
  .error {
    margin-top: var(--space-1);
    font-size: var(--fs-s);
    color: var(--danger);
  }
  .unsure {
    flex: none;
    padding: 2px var(--space-2);
    border-radius: var(--radius-s);
    background: var(--warn-soft);
    color: var(--warn);
    font-size: var(--fs-xs);
    font-weight: 600;
  }
  .working {
    color: var(--text-muted);
    padding: 0 var(--space-2);
  }
</style>
